#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
端到端检索演示（模拟阶段 2 核心流程）：
  1. 取一张文物图（模拟用户上传）
  2. DINOv2 提取特征
  3. FAISS 检索 Top-5 相似文物
  4. Neo4j 查询每个相似文物的时期/文化（证据链）
"""

import json
import os
from pathlib import Path

import faiss
import numpy as np
import pandas as pd
import torch
from neo4j import GraphDatabase
from PIL import Image
from transformers import AutoImageProcessor, AutoModel

ROOT = Path(__file__).resolve().parents[1]
FEATURE_DIR = ROOT / "data" / "features"
METADATA_CSV = ROOT / "data" / "raw" / "metadata.csv"
MODEL_NAME = "facebook/dinov2-base"


def extract_feature(model, processor, img_path):
    """DINOv2 提取单图特征并 L2 归一化"""
    img = Image.open(img_path).convert("RGB")
    inputs = processor(images=img, return_tensors="pt")
    with torch.no_grad():
        out = model(**inputs)
    f = out.last_hidden_state[:, 0].numpy()[0]
    return f / np.linalg.norm(f)


def main():
    # 1. 加载索引 + 映射 + 元数据
    index = faiss.read_index(str(FEATURE_DIR / "dinov2_hnsw.index"))
    id_map = json.load(open(FEATURE_DIR / "id_map.json", encoding="utf-8"))
    df = pd.read_csv(METADATA_CSV)
    meta_by_path = {str(r["image_path"]): r for _, r in df.iterrows()}

    # 2. 加载 DINOv2（模拟上传后的特征提取）
    print("加载 DINOv2 模型...")
    model = AutoModel.from_pretrained(MODEL_NAME)
    model.eval()
    processor = AutoImageProcessor.from_pretrained(MODEL_NAME)

    # 3. 选一张查询图（模拟用户上传）
    query_path = id_map[150]
    q_meta = meta_by_path.get(query_path, {})
    print("\n=== 查询文物 ===")
    print("  图片:", query_path.split("/")[-1])
    print("  名称:", q_meta.get("title", "-"))
    print("  文化:", q_meta.get("culture", "-"), "| 时期:", q_meta.get("period", "-"))

    # 4. 提取特征 + 检索
    q_vec = extract_feature(model, processor, query_path)
    D, I = index.search(q_vec[None, :], 6)  # Top-6（含自己）
    print("\n=== 相似文物 Top-6（相似度）===")

    # 5. Neo4j 图谱查询
    driver = GraphDatabase.driver(
        "bolt://neo4j:7687", auth=("neo4j", os.environ.get("NEO4J_PASSWORD", ""))
    )
    with driver.session() as session:
        for rank, (j, score) in enumerate(zip(I[0], D[0]), 1):
            path = id_map[j]
            meta = meta_by_path.get(path, {})
            oid = path.split("/")[-1].replace(".jpg", "")
            # 图谱查询
            rec = session.run(
                "MATCH (a:Artifact {object_id:$oid}) "
                "OPTIONAL MATCH (a)-[:BELONGS_TO]->(p:Period) "
                "OPTIONAL MATCH (a)-[:BELONGS_TO_CULTURE]->(c:Culture) "
                "RETURN p.name AS period, c.name AS culture",
                oid=oid,
            ).data()
            kg = rec[0] if rec else {}
            tag = "（← 查询图自己）" if j == 150 else ""
            print(
                "  {}. {}  相似度={:.3f}{}".format(
                    rank, path.split("/")[-1], score, tag
                )
            )
            print(
                "     名称: {} | 文化: {} | 时期: {}".format(
                    meta.get("title", "-"),
                    kg.get("culture") or meta.get("culture", "-"),
                    kg.get("period") or meta.get("period", "-"),
                )
            )
    driver.close()


if __name__ == "__main__":
    main()
