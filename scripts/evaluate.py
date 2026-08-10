#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检索质量评估脚本（阶段 2 · 任务 2.4）

方法：
  用 metadata 的 culture（文化）作为"同类"标准（无需人工标注）。
  对每个有文化标签的文物做一次 Top-5 检索（排除自身），
  统计结果中"同类文化"的命中情况，计算 Precision@5 / Recall@5。

说明：
  - 直接复用已算好的特征向量（dinov2_features.npy），评估秒级完成
  - 真值是"文化"近似（数据中约 70% 文物无 culture，仅评估有标签部分）

运行：
  docker compose run --rm app python scripts/evaluate.py
"""
import json
from pathlib import Path

import faiss
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FEATURE_DIR = ROOT / "data" / "features"
METADATA_CSV = ROOT / "data" / "raw" / "metadata.csv"
TOP_K = 5


def oid_from_path(p: str) -> str:
    """从 image_path 提取 object_id（如 /app/data/raw/images/36444.jpg -> 36444）"""
    return p.split("/")[-1].replace(".jpg", "")


def main():
    df = pd.read_csv(METADATA_CSV)
    vecs = np.load(FEATURE_DIR / "dinov2_features.npy")
    with open(FEATURE_DIR / "id_map.json", "r", encoding="utf-8") as f:
        id_map = json.load(f)
    index = faiss.read_index(str(FEATURE_DIR / "dinov2_hnsw.index"))

    # object_id -> 行（快速查找元数据）
    meta_by_oid = {str(r["object_id"]): r for _, r in df.iterrows()}

    # 预处理：每条记录的 culture（strip + 去 nan）
    oid_culture = {}
    for oid, row in meta_by_oid.items():
        c = str(row.get("culture", "")).strip()
        oid_culture[oid] = c if c and c != "nan" else ""

    # 预计算各文化的文物数量（用于 Recall 分母）
    culture_total = {}
    for c in oid_culture.values():
        if c:
            culture_total[c] = culture_total.get(c, 0) + 1

    precisions, recalls, hits, totals = [], [], [], []
    queried = 0

    for i, path in enumerate(id_map):
        oid = oid_from_path(path)
        culture = oid_culture.get(oid, "")
        if not culture:
            continue                       # 无标签，跳过
        total_related = culture_total[culture] - 1
        if total_related <= 0:
            continue                       # 该文化只有自己，无法评估

        # 检索 Top-(K+1)（含自己，结果按相似度降序）
        _, idx = index.search(vecs[i:i + 1], TOP_K + 1)
        results = [j for j in idx[0] if j != i][:TOP_K]    # 排除自身

        # 统计同类命中
        hits_n = 0
        for j in results:
            r_oid = oid_from_path(id_map[j])
            if oid_culture.get(r_oid, "") == culture:
                hits_n += 1

        precisions.append(hits_n / TOP_K)
        recalls.append(hits_n / total_related)
        hits.append(hits_n)
        totals.append(total_related)
        queried += 1

    # 报告
    print("=" * 50)
    print(f"评估文物数（有 culture 标签）: {queried}")
    print(f"Top-K: {TOP_K}")
    print("-" * 50)
    print(f"Precision@{TOP_K}: {np.mean(precisions):.3f}  (Top-{TOP_K} 中同类占比均值)")
    print(f"Recall@{TOP_K}:    {np.mean(recalls):.3f}  (检索到的同类 / 同类总数)")
    print(f"平均命中同类数:    {np.mean(hits):.2f} / {TOP_K}")
    print(f"平均同类总数:      {np.mean(totals):.1f}")
    print("=" * 50)

    # 按文化分组看表现（便于定位问题）
    print("\n按文化分组的平均命中数（Top-5 中的同类数）:")
    by_culture = {}
    for i, path in enumerate(id_map):
        oid = oid_from_path(path)
        culture = oid_culture.get(oid, "")
        if not culture or culture_total.get(culture, 0) <= 1:
            continue
        _, idx = index.search(vecs[i:i + 1], TOP_K + 1)
        results = [j for j in idx[0] if j != i][:TOP_K]
        hits_n = sum(1 for j in results if oid_culture.get(oid_from_path(id_map[j]), "") == culture)
        by_culture.setdefault(culture, []).append(hits_n)
    for c, hs in sorted(by_culture.items(), key=lambda x: -np.mean(x[1])):
        print(f"  {c:<20} 样本 {len(hs):>3}  平均同类命中 {np.mean(hs):.2f}/{TOP_K}")


if __name__ == "__main__":
    main()
