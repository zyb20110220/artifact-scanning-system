#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知识图谱构建与导入脚本（阶段 1 · 任务 1.5）

功能：
  1. 从 metadata.csv 构建 Artifact / Culture / Period 节点与关系
  2. 用 Wikidata SPARQL 补全 Culture/Period 的时间范围（P580/P582）与 QID
  3. 导入 Neo4j（MERGE 幂等，可重复执行）

图谱模式：
  (:Artifact {object_id, title, image_path, ...})
      -[:BELONGS_TO]->(:Period {name, qid, start, end})
      -[:BELONGS_TO_CULTURE]->(:Culture {name, qid, start, end})

用法（在容器内运行）：
  docker compose run --rm app python scripts/build_kg.py
"""

import logging
import os
import time
from pathlib import Path

import pandas as pd
import requests
import yaml
from neo4j import GraphDatabase

# ---------- 路径 ----------
ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "config.yaml"
METADATA_CSV = ROOT / "data" / "raw" / "metadata.csv"
WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"

# ---------- 日志 ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def normalize(term):
    """归一化：提取括号前的主干，如 'Tang dynasty (618–907)' -> 'Tang dynasty'"""
    return term.split("(")[0].strip()


def query_wikidata(terms):
    """
    批量查询 terms 在 Wikidata 的实体、QID 与时间范围（P580/P582）。
    返回 {normalized_term: {qid, wd_label, start, end}}
    """
    result = {}
    for i in range(0, len(terms), 15):          # 分块，避免 URL 过长
        chunk = terms[i:i + 15]
        labels = " ".join(f'"{t}"@en' for t in chunk)
        query = f"""
        SELECT ?label ?ent ?entLabel ?start ?end WHERE {{
          VALUES ?label {{ {labels} }}
          ?ent rdfs:label ?label .
          OPTIONAL {{ ?ent wdt:P580 ?start }}
          OPTIONAL {{ ?ent wdt:P582 ?end }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}
        """
        r = requests.get(
            WIKIDATA_ENDPOINT,
            params={"query": query, "format": "json"},
            timeout=60,
            headers={"User-Agent": "artifact-scanning/1.0"},
        )
        r.raise_for_status()

        # 按 label 分组（同 label 可能命中多个实体）
        grouped = {}
        for b in r.json()["results"]["bindings"]:
            label = b["label"]["value"]
            rec = {
                "qid": b.get("ent", {}).get("value", "").split("/")[-1],
                "wd_label": b.get("entLabel", {}).get("value", ""),
                "start": b.get("start", {}).get("value", ""),
                "end": b.get("end", {}).get("value", ""),
            }
            grouped.setdefault(label, []).append(rec)
        # 同 label 多实体时，优先选带时间范围的
        for label, recs in grouped.items():
            recs.sort(key=lambda x: 0 if x["start"] else 1)
            result[label] = recs[0]
        time.sleep(0.5)                          # 温和请求
    return result


def main():
    cfg = load_config()
    kg_cfg = cfg["kg"]
    df = pd.read_csv(METADATA_CSV)
    logger.info("读取文物: %d 件", len(df))

    # 1. 归一化 culture/period -> 节点集合
    #    norm_map: 归一化名 -> {(列名, 原始词), ...}
    norm_map = {}
    for col in ("culture", "period"):
        for val in df[col].dropna():
            s = str(val).strip()
            if s:
                norm_map.setdefault(normalize(s), set()).add((col, s))
    logger.info("归一化后唯一实体: %d 个（culture + period）", len(norm_map))

    # 2. Wikidata 补全时间范围
    logger.info("查询 Wikidata 补全 ...")
    wd = query_wikidata(sorted(norm_map.keys()))
    matched = sum(1 for n in norm_map if n in wd)
    logger.info("Wikidata 匹配: %d/%d", matched, len(norm_map))

    # 3. 导入 Neo4j
    uri = kg_cfg["uri"]
    password = os.environ.get("NEO4J_PASSWORD", "")
    logger.info("连接 Neo4j: %s", uri)
    driver = GraphDatabase.driver(uri, auth=(kg_cfg["user"], password))
    try:
        with driver.session() as session:
            # 清空旧图（可重复执行）
            session.run("MATCH (n) DETACH DELETE n")
            logger.info("已清空旧图谱")

            # 唯一性约束：防止重复节点，保证 MERGE 幂等
            session.run(
                "CREATE CONSTRAINT artifact_id IF NOT EXISTS "
                "FOR (a:Artifact) REQUIRE a.object_id IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT culture_name IF NOT EXISTS "
                "FOR (c:Culture) REQUIRE c.name IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT period_name IF NOT EXISTS "
                "FOR (p:Period) REQUIRE p.name IS UNIQUE"
            )

            # ---- 阶段 1：建所有节点（先节点后关系，避免 MERGE 误建）----
            for _, row in df.iterrows():
                session.run(
                    "MERGE (a:Artifact {object_id: $oid}) "
                    "SET a.title=$title, a.image_path=$img, a.medium=$medium, "
                    "    a.object_date=$date, a.culture_raw=$culture, a.period_raw=$period",
                    oid=str(row["object_id"]), title=str(row.get("title", "")),
                    img=str(row.get("image_path", "")), medium=str(row.get("medium", "")),
                    date=str(row.get("object_date", "")),
                    culture=str(row.get("culture", "")), period=str(row.get("period", "")),
                )

            for norm, items in norm_map.items():
                info = wd.get(norm, {})
                props = {
                    "qid": info.get("qid", ""),
                    "wd_label": info.get("wd_label", ""),
                    "start": info.get("start", ""),
                    "end": info.get("end", ""),
                }
                has_culture = any(col == "culture" for col, _ in items)
                has_period = any(col == "period" for col, _ in items)
                if has_culture:
                    session.run(
                        "MERGE (c:Culture {name:$name}) "
                        "ON CREATE SET c += $props ON MATCH SET c += $props",
                        name=norm, props=props,
                    )
                if has_period:
                    session.run(
                        "MERGE (p:Period {name:$name}) "
                        "ON CREATE SET p += $props ON MATCH SET p += $props",
                        name=norm, props=props,
                    )

            # ---- 阶段 2：建关系（MATCH 已存在的唯一节点，再 MERGE 关系）----
            for _, row in df.iterrows():
                oid = str(row["object_id"])
                c = str(row.get("culture", "")).strip()
                if c:
                    session.run(
                        "MATCH (a:Artifact {object_id:$oid}) "
                        "MATCH (c:Culture {name:$name}) "
                        "MERGE (a)-[:BELONGS_TO_CULTURE]->(c)",
                        oid=oid, name=normalize(c),
                    )
                p = str(row.get("period", "")).strip()
                if p:
                    session.run(
                        "MATCH (a:Artifact {object_id:$oid}) "
                        "MATCH (p:Period {name:$name}) "
                        "MERGE (a)-[:BELONGS_TO]->(p)",
                        oid=oid, name=normalize(p),
                    )
            logger.info("导入完成")

            # 3.3 统计验证
            counts = session.run(
                "MATCH (n) RETURN labels(n)[0] AS lbl, count(*) AS c ORDER BY c DESC"
            ).data()
            for row in counts:
                logger.info("  节点 %-10s: %d", row["lbl"], row["c"])
            rels = session.run("MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c").data()
            for row in rels:
                logger.info("  关系 %-22s: %d", row["t"], row["c"])
    finally:
        driver.close()


if __name__ == "__main__":
    main()
