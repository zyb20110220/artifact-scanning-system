#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
特征权重实验（阶段 2 · 检索优化）

测 DINOv2(768) 与 CLIP(512) 在不同权重组合下拼接的检索精度（culture P@5），
找出最优权重。直接复用已算好的特征文件，秒级完成，无需模型。

用法（在容器内运行）：
  docker compose run --rm app python scripts/experiment_weights.py
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
    return p.split("/")[-1].replace(".jpg", "")


def eval_standard(vecs, id_map, df, standard="culture"):
    """返回 Precision@5（同类标准）"""
    vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
    index = faiss.IndexHNSWFlat(vecs.shape[1], 32, faiss.METRIC_INNER_PRODUCT)
    index.add(vecs)
    meta_by_oid = {str(r["object_id"]): r for _, r in df.iterrows()}
    oid_label = {}
    label_total = {}
    for oid, row in meta_by_oid.items():
        v = str(row.get(standard, "")).strip()
        if v and v.lower() != "nan":
            oid_label[oid] = v
            label_total[v] = label_total.get(v, 0) + 1

    precisions = []
    for i in range(len(id_map)):
        oid = oid_from_path(id_map[i])
        label = oid_label.get(oid, "")
        if not label:
            continue
        _, idx = index.search(vecs[i:i + 1], TOP_K + 1)
        results = [j for j in idx[0] if j != i][:TOP_K]
        hits = sum(1 for j in results if oid_label.get(oid_from_path(id_map[j]), "") == label)
        precisions.append(hits / TOP_K)
    return np.mean(precisions) if precisions else 0.0


def main():
    df = pd.read_csv(METADATA_CSV)
    id_map = json.loads((FEATURE_DIR / "id_map.json").read_text(encoding="utf-8"))
    d = np.load(FEATURE_DIR / "dinov2_features.npy")          # (N, 768) 已归一化
    h = np.load(FEATURE_DIR / "hybrid_features.npy")          # (N, 1280) 前768=DINOv2 后512=CLIP
    c = h[:, 768:]                                            # (N, 512)

    print(f"{'权重 (D, C)':<16} {'culture P@5':<12} {'period P@5':<12} {'medium P@5':<12}")
    combos = [
        (1.0, 0.0), (0.0, 1.0), (1.0, 1.0), (0.5, 1.0),
        (0.3, 1.0), (0.2, 1.0), (0.5, 1.5), (0.3, 1.5),
    ]
    for wd, wc in combos:
        # 拼接（concatenate）后整体 L2 归一化；权重控制两部分相对幅度
        vecs = np.concatenate([d * wd, c * wc], axis=1)
        p_c = eval_standard(vecs, id_map, df, "culture")
        p_p = eval_standard(vecs, id_map, df, "period")
        p_m = eval_standard(vecs, id_map, df, "medium")
        print(f"({wd}, {wc})".ljust(16), f"{p_c:.3f}".ljust(12), f"{p_p:.3f}".ljust(12), f"{p_m:.3f}".ljust(12))


if __name__ == "__main__":
    main()
