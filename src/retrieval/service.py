#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检索服务（阶段 2 · 任务 2.1）

组合"特征提取 + FAISS 检索"为高层服务：
  输入一张图片路径 → 输出 Top-K 相似文物（含路径 + 相似度）
供后续 Gradio 界面直接调用。
"""
from pathlib import Path

import yaml

from src.features.dinov2 import extract_feature
from src.retrieval.faiss_index import search

ROOT = Path(__file__).resolve().parents[2]          # src/retrieval/ -> 项目根


def load_config():
    with open(ROOT / "config" / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class ArtifactSearchService:
    """文物检索服务：封装图片检索的核心流程"""

    def __init__(self, config_path=None):
        cfg = load_config() if config_path is None else _load(config_path)
        retr = cfg["retrieval"]
        feat = cfg["features"]
        self.top_k = retr.get("top_k", 5)
        self.model_name = feat.get("dinov2_model", "facebook/dinov2-base")
        self.index_path = ROOT / retr["index_path"]
        self.id_map_path = ROOT / retr["id_map_path"]

    def search_by_image(self, image_path, top_k=None):
        """核心入口：图片路径 → Top-K 相似文物"""
        k = top_k or self.top_k
        # 1. 特征提取
        vec = extract_feature(image_path, model_name=self.model_name)
        # 2. FAISS 检索
        results = search(vec, top_k=k, index_path=self.index_path, id_map_path=self.id_map_path)
        return results


def _load(config_path):
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
