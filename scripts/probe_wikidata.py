#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任务 1.5 探测：验证本地 culture/period 词能否在 Wikidata 匹配到实体。
仅做匹配率报告，不导入 Neo4j。
"""
import logging
import time
from pathlib import Path

import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
METADATA_CSV = ROOT / "data" / "raw" / "metadata.csv"
WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"


def query_wikidata(terms):
    """VALUES 批量查询 terms 在 Wikidata 的 label 精确匹配实体"""
    result = {}
    for i in range(0, len(terms), 15):          # 分块，避免 URL 过长
        chunk = terms[i:i + 15]
        labels = " ".join(f'"{t}"@en' for t in chunk)
        query = f"""
        SELECT ?label ?ent ?entLabel WHERE {{
          VALUES ?label {{ {labels} }}
          ?ent rdfs:label ?label .
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
        for b in r.json()["results"]["bindings"]:
            label = b["label"]["value"]
            ent = b.get("ent", {}).get("value", "")
            ent_label = b.get("entLabel", {}).get("value", "")
            result[label] = {"qid": ent.split("/")[-1], "wd_label": ent_label}
        time.sleep(0.5)                          # 温和请求
    return result


def normalize(term):
    """归一化：提取括号前的主干，如 "Tang dynasty (618–907)" -> "Tang dynasty" """
    return term.split("(")[0].strip()


def main():
    df = pd.read_csv(METADATA_CSV)
    cultures = sorted({str(c).strip() for c in df["culture"].dropna() if str(c).strip()})
    periods = sorted({str(p).strip() for p in df["period"].dropna() if str(p).strip()})

    # 归一化：normalized -> 覆盖的原始词列表
    norm_map = {}
    for t in cultures + periods:
        norm_map.setdefault(normalize(t), []).append(t)
    normalized = sorted(norm_map.keys())
    logger.info("原始词: Culture %d + Period %d | 归一化后: %d 个", len(cultures), len(periods), len(normalized))

    logger.info("查询 Wikidata 匹配（归一化后）...")
    wd = query_wikidata(normalized)

    matched_orig = 0
    for n, origs in norm_map.items():
        hit = wd.get(n)
        status = "OK" if hit else "--"
        matched_orig += len(origs) if hit else 0
        logger.info("  [%s] %-40s -> %s | 覆盖原始词: %s",
                    status, n, hit["wd_label"] if hit else "(无匹配)", ", ".join(origs[:3]))
    logger.info("=== 汇总 ===")
    logger.info("归一化词匹配: %d/%d", sum(1 for n in norm_map if n in wd), len(norm_map))
    logger.info("覆盖原始词: %d/%d", matched_orig, len(cultures) + len(periods))


if __name__ == "__main__":
    main()
