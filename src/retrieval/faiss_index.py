#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FAISS 检索模块（阶段 2 · 任务 2.1）

提供索引加载与最近邻搜索的复用函数。
索引与 id_map 首次加载后缓存，避免重复读盘。
"""
import json
from pathlib import Path

import faiss
import numpy as np

# 模块级缓存
_index = None
_id_map = None


def load_index(index_path, id_map_path):
    """加载（或复用）FAISS 索引与 id_map"""
    global _index, _id_map
    if _index is None:
        _index = faiss.read_index(str(index_path))
        with open(id_map_path, "r", encoding="utf-8") as f:
            _id_map = json.load(f)
    return _index, _id_map


def search(feature: np.ndarray, top_k: int = 5, index_path=None, id_map_path=None):
    """
    在索引中检索与 feature 最相似的 top_k 个向量。
    参数：
      feature:   (768,) L2 归一化向量
      top_k:     返回数量
    返回：
      [{"image_path": str, "score": float}, ...]  按相似度降序
    """
    index, id_map = load_index(index_path, id_map_path)
    scores, idx = index.search(feature[None, :], top_k)   # 转 2D 查询
    results = []
    for s, i in zip(scores[0], idx[0]):
        results.append({"image_path": id_map[i], "score": float(s)})
    return results
