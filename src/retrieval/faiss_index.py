#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FAISS 检索模块（阶段 2 · 任务 2.1 / Rerank 优化）

提供索引加载与最近邻搜索的复用函数。
索引与 id_map 首次加载后缓存，避免重复读盘。
支持两阶段 Rerank：粗筛 Top-N → 用"高 CLIP 权重混合分数"精排 → Top-K
（实验证明：culture P@5 0.316 → 0.343）。
"""
import json
from pathlib import Path

import faiss
import numpy as np

# 模块级缓存
_index = None
_id_map = None
_vecs = None


def load_index(index_path, id_map_path, vecs_path=None):
    """加载（或复用）FAISS 索引、id_map 与向量矩阵（供 Rerank 精排）"""
    global _index, _id_map, _vecs
    if _index is None:
        _index = faiss.read_index(str(index_path))
        with open(id_map_path, "r", encoding="utf-8") as f:
            _id_map = json.load(f)
        if vecs_path and Path(vecs_path).exists():
            _vecs = np.load(str(vecs_path))
    return _index, _id_map


def search(
    feature: np.ndarray,
    top_k: int = 5,
    index_path=None,
    id_map_path=None,
    vecs_path=None,
    top_n: int = None,
    wd: float = 0.2,
    wc: float = 1.0,
):
    """
    在索引中检索与 feature 最相似的 top_k 个向量。
    参数：
      feature:  L2 归一化向量（768 维 DINOv2，或 1280 维混合 DINOv2+CLIP）
      top_k:    最终返回数量
      top_n:    粗筛数量（>top_k 且提供 vecs_path 时启用 Rerank）
      wd, wc:   精排时 DINOv2 / CLIP 分量的权重（混合特征时生效）
    返回：
      [{"image_path": str, "score": float}, ...]  按相似度降序
    """
    index, id_map = load_index(index_path, id_map_path, vecs_path)

    # Rerank 路径：粗筛 Top-N → 高 CLIP 权重精排 → Top-K
    if top_n and top_n > top_k and _vecs is not None and feature.shape[0] >= 768:
        scores, idx = index.search(feature[None, :], top_n)   # 粗筛（排除自身由调用方处理）
        ranked = []
        q_d, q_c = feature[:768] * wd, feature[768:] * wc      # 查询向量拆分加权
        for i in idx[0]:
            v = _vecs[i]
            v_d, v_c = v[:768] * wd, v[768:] * wc
            score = float(np.dot(q_d, v_d) + np.dot(q_c, v_c))
            ranked.append((i, score))
        ranked.sort(key=lambda x: -x[1])                       # 精排降序
        return [{"image_path": id_map[i], "score": s} for i, s in ranked[:top_k]]

    # 默认路径：直接 Top-K
    scores, idx = index.search(feature[None, :], top_k)   # 转 2D 查询
    results = []
    for s, i in zip(scores[0], idx[0]):
        results.append({"image_path": id_map[i], "score": float(s)})
    return results
