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
import argparse
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
    parser = argparse.ArgumentParser(description="检索质量评估")
    parser.add_argument("--standard", default="culture",
                        choices=["culture", "period", "medium"],
                        help="同类判定标准（默认 culture）")
    parser.add_argument("--feature-file", default="dinov2_features.npy",
                        help="特征 npy 文件名（混合特征传 hybrid_features.npy）")
    parser.add_argument("--index-file", default="dinov2_hnsw.index",
                        help="FAISS 索引文件名（混合特征传 hybrid_hnsw.index）")
    parser.add_argument("--rerank-top-n", type=int, default=None,
                        help="启用 Rerank：粗筛 Top-N → 高 CLIP 权重精排（需 1280 维混合特征）")
    parser.add_argument("--rerank-wd", type=float, default=0.2, help="Rerank DINOv2 权重")
    parser.add_argument("--rerank-wc", type=float, default=1.0, help="Rerank CLIP 权重")
    args = parser.parse_args()
    standard = args.standard

    df = pd.read_csv(METADATA_CSV)
    vecs = np.load(FEATURE_DIR / args.feature_file)
    with open(FEATURE_DIR / "id_map.json", "r", encoding="utf-8") as f:
        id_map = json.load(f)
    index = faiss.read_index(str(FEATURE_DIR / args.index_file))
    print(f"[特征] {args.feature_file} | [索引] {args.index_file} | 向量数 {vecs.shape[0]}, 维度 {vecs.shape[1]}")

    # object_id -> 行（快速查找元数据）
    meta_by_oid = {str(r["object_id"]): r for _, r in df.iterrows()}

    # 预处理：每条记录的标签（按 standard 字段，strip + 去 nan）
    oid_label = {}
    for oid, row in meta_by_oid.items():
        c = str(row.get(standard, "")).strip()
        oid_label[oid] = c if c and c != "nan" else ""

    # 预计算各标签的文物数量（用于 Recall 分母）
    label_total = {}
    for c in oid_label.values():
        if c:
            label_total[c] = label_total.get(c, 0) + 1

    precisions, recalls, hits, totals = [], [], [], []
    queried = 0

    for i, path in enumerate(id_map):
        oid = oid_from_path(path)
        label = oid_label.get(oid, "")
        if not label:
            continue                       # 无标签，跳过
        total_related = label_total[label] - 1
        if total_related <= 0:
            continue                       # 该类只有自己，无法评估

        # 检索（可选 Rerank：粗筛 Top-N → 高 CLIP 权重精排 → Top-K）
        if args.rerank_top_n and vecs.shape[1] >= 768:
            _, idx = index.search(vecs[i:i + 1], args.rerank_top_n + 1)
            cand = [j for j in idx[0] if j != i][:args.rerank_top_n]
            q = np.concatenate([vecs[i, :768] * args.rerank_wd, vecs[i, 768:] * args.rerank_wc])
            c = np.concatenate([
                vecs[cand, :768] * args.rerank_wd, vecs[cand, 768:] * args.rerank_wc
            ], axis=1)
            sc = q @ c.T
            order = np.argsort(-sc)[:TOP_K]
            results = [cand[o] for o in order]
        else:
            _, idx = index.search(vecs[i:i + 1], TOP_K + 1)
            results = [j for j in idx[0] if j != i][:TOP_K]    # 排除自身

        # 统计同类命中
        hits_n = 0
        for j in results:
            r_oid = oid_from_path(id_map[j])
            if oid_label.get(r_oid, "") == label:
                hits_n += 1

        precisions.append(hits_n / TOP_K)
        recalls.append(hits_n / total_related)
        hits.append(hits_n)
        totals.append(total_related)
        queried += 1

    # 报告
    print("=" * 50)
    print(f"评估文物数（有 {standard} 标签）: {queried}")
    print(f"Top-K: {TOP_K}")
    print("-" * 50)
    print(f"Precision@{TOP_K}: {np.mean(precisions):.3f}  (Top-{TOP_K} 中同类占比均值)")
    print(f"Recall@{TOP_K}:    {np.mean(recalls):.3f}  (检索到的同类 / 同类总数)")
    print(f"平均命中同类数:    {np.mean(hits):.2f} / {TOP_K}")
    print(f"平均同类总数:      {np.mean(totals):.1f}")
    print("=" * 50)

    # 按标签分组看表现（便于定位问题）
    print(f"\n按 {standard} 分组的平均命中数（Top-5 中的同类数）:")
    by_label = {}
    for i, path in enumerate(id_map):
        oid = oid_from_path(path)
        label = oid_label.get(oid, "")
        if not label or label_total.get(label, 0) <= 1:
            continue
        _, idx = index.search(vecs[i:i + 1], TOP_K + 1)
        results = [j for j in idx[0] if j != i][:TOP_K]
        hits_n = sum(1 for j in results if oid_label.get(oid_from_path(id_map[j]), "") == label)
        by_label.setdefault(label, []).append(hits_n)
    for c, hs in sorted(by_label.items(), key=lambda x: -np.mean(x[1])):
        print(f"  {c:<24} 样本 {len(hs):>3}  平均同类命中 {np.mean(hs):.2f}/{TOP_K}")


if __name__ == "__main__":
    main()
