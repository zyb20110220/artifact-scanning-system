#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rerank 实验（阶段 2 · 检索优化）

验证"粗筛 Top-50 → 精排 → Top-5"能否提升 culture P@5。
精排策略候选：
  A. 基线：混合特征直接 Top-5（不 Rerank）
  B. 粗筛 Top-50 → 用 CLIP 语义分数重排
  C. 粗筛 Top-50 → 用精确内积重排（修正 HNSW 近似误差）
  D. 粗筛 Top-50 → 用高 CLIP 权重混合分数重排

用法（在容器内运行）：
  docker compose run --rm app python scripts/experiment_rerank.py
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
RERANK_N = 50


def oid_from_path(p: str) -> str:
    return p.split("/")[-1].replace(".jpg", "")


def load_labels(df, standard):
    meta = {str(r["object_id"]): r for _, r in df.iterrows()}
    oid_label, label_total = {}, {}
    for oid, row in meta.items():
        v = str(row.get(standard, "")).strip()
        if v and v.lower() != "nan":
            oid_label[oid] = v
            label_total[v] = label_total.get(v, 0) + 1
    return oid_label


def evaluate(method, vecs, id_map, df, standard="culture"):
    """对每个有标签样本检索 Top-5，返回 Precision@5"""
    vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
    # 粗筛索引：HNSW Top-RERANK_N
    index = faiss.IndexHNSWFlat(vecs.shape[1], 32, faiss.METRIC_INNER_PRODUCT)
    index.add(vecs)
    oid_label = load_labels(df, standard)
    precisions = []
    for i in range(len(id_map)):
        oid = oid_from_path(id_map[i])
        label = oid_label.get(oid, "")
        if not label:
            continue
        # 粗筛 Top-RERANK_N（排除自身）
        _, idx = index.search(vecs[i:i + 1], RERANK_N + 1)
        cand = [j for j in idx[0] if j != i][:RERANK_N]
        # 精排
        if method == "A":            # 直接取粗筛 Top-5
            ranked = cand[:TOP_K]
        elif method == "B":          # 用 CLIP 分数重排
            clip_q = vecs[i, 768:]
            clip_c = vecs[cand, 768:]
            scores = clip_q @ clip_c.T
            order = np.argsort(-scores)[:TOP_K]
            ranked = [cand[o] for o in order]
        elif method == "C":          # 精确内积重排（全 1280 维）
            scores = vecs[i] @ vecs[cand].T
            order = np.argsort(-scores)[:TOP_K]
            ranked = [cand[o] for o in order]
        elif method == "D":          # 高 CLIP 权重混合分数重排
            q = np.concatenate([vecs[i, :768] * 0.2, vecs[i, 768:] * 1.0])
            c = np.concatenate([vecs[cand, :768] * 0.2, vecs[cand, 768:] * 1.0], axis=1)
            scores = q @ c.T
            order = np.argsort(-scores)[:TOP_K]
            ranked = [cand[o] for o in order]
        hits = sum(1 for j in ranked if oid_label.get(oid_from_path(id_map[j]), "") == label)
        precisions.append(hits / TOP_K)
    return np.mean(precisions)


def main():
    df = pd.read_csv(METADATA_CSV)
    id_map = json.loads((FEATURE_DIR / "id_map.json").read_text(encoding="utf-8"))
    vecs = np.load(FEATURE_DIR / "hybrid_features.npy")     # (N,1280) 前768 DINOv2 后512 CLIP
    print(f"向量数: {len(vecs)}, 维度: {vecs.shape[1]}")
    print(f"{'方法':<28} {'culture P@5':<12} {'period P@5':<12} {'medium P@5':<12}")
    for method, desc in [
        ("A", "A: 混合直接Top-5(基线)"),
        ("B", "B: 粗筛Top-50→CLIP重排"),
        ("C", "C: 粗筛Top-50→精确内积重排"),
        ("D", "D: 粗筛Top-50→高CLIP权重重排"),
    ]:
        p_c = evaluate(method, vecs, id_map, df, "culture")
        p_p = evaluate(method, vecs, id_map, df, "period")
        p_m = evaluate(method, vecs, id_map, df, "medium")
        print(f"{desc:<28} {p_c:.3f}".ljust(12), f"{p_p:.3f}".ljust(12), f"{p_m:.3f}".ljust(12))


if __name__ == "__main__":
    main()
