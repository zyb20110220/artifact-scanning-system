#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FAISS 索引构建脚本（阶段 1 · 任务 1.4）

功能：
  1. 读取特征 npy（299, 768）
  2. 构建 HNSW 索引（邻居数 m 从 config 读取）
  3. 保存索引到 data/features/dinov2_hnsw.index
  4. 自测检索：验证 Top-1 能找回自身

用法（在容器内运行）：
  docker compose run --rm app python scripts/build_index.py
"""

import argparse
import json
import logging
from pathlib import Path

import faiss
import numpy as np
import yaml

# ---------- 路径 ----------
ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "config.yaml"
FEATURE_DIR = ROOT / "data" / "features"

# ---------- 日志 ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_index(vectors, hnsw_m, metric):
    """
    构建 HNSW 索引。
      metric="l2" : 欧氏距离（向量已 L2 归一化，排序与余弦等价）
      metric="ip" : 内积（归一化后 = 余弦相似度，分数可直接当相似度）
    """
    dim = vectors.shape[1]
    if metric == "ip":
        index = faiss.IndexHNSWFlat(dim, hnsw_m, faiss.METRIC_INNER_PRODUCT)
        logger.info("索引类型: HNSW(IP/余弦), 维度 %d, 邻居 m=%d", dim, hnsw_m)
    else:
        index = faiss.IndexHNSWFlat(dim, hnsw_m)
        logger.info("索引类型: HNSW(L2), 维度 %d, 邻居 m=%d", dim, hnsw_m)
    index.add(vectors)
    return index


def self_check(index, vectors, id_map):
    """
    自测：对前 N 个向量做 Top-2 检索。
    归一化后自身相似度应≈1（或距离≈0），且 Top-1 应该是自己。
    """
    n_check = min(5, len(vectors))
    logger.info("=== 自测检索（前 %d 个）===", n_check)
    scores, idx = index.search(vectors[:n_check], 2)
    ok = 0
    for i in range(n_check):
        top1 = idx[i][0]
        is_self = (top1 == i)
        if is_self:
            ok += 1
        logger.info(
            "查询 %s -> Top-1 是自身? %s | 相似度=%.4f | Top-1路径: %s",
            id_map[i].split("/")[-1], is_self, scores[i][0], id_map[top1].split("/")[-1],
        )
    logger.info("自测通过: %d/%d", ok, n_check)
    return ok == n_check


def main():
    parser = argparse.ArgumentParser(description="构建 FAISS HNSW 索引")
    parser.add_argument("--metric", default=None, help="l2 / ip（覆盖 config）")
    parser.add_argument("--feature-file", default=None,
                        help="特征 npy 文件名（默认 dinov2_features.npy；混合特征传 hybrid_features.npy）")
    args = parser.parse_args()

    cfg = load_config()["retrieval"]
    hnsw_m = cfg.get("hnsw_m", 32)
    metric = args.metric or cfg.get("metric", "l2")
    index_path = ROOT / cfg.get("index_path", "data/features/dinov2_hnsw.index")
    id_map_path = ROOT / cfg.get("id_map_path", "data/features/id_map.json")

    # 1. 读取特征
    feature_file = args.feature_file or "dinov2_features.npy"
    vectors = np.load(FEATURE_DIR / feature_file)
    logger.info("特征文件: %s | %s", feature_file, vectors.shape)

    # 2. 读取 id_map（向量索引 → 图片路径）
    with open(id_map_path, "r", encoding="utf-8") as f:
        id_map = json.load(f)
    logger.info("id_map 数量: %d", len(id_map))

    # 3. 构建索引
    index = build_index(vectors, hnsw_m, metric)
    logger.info("索引向量数: %d", index.ntotal)

    # 4. 保存
    index_path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_path))
    logger.info("索引已保存 → %s", index_path)

    # 5. 自测
    self_check(index, vectors, id_map)


if __name__ == "__main__":
    main()
