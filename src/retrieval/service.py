#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检索服务（阶段 2 · 任务 2.1）

组合"特征提取 + FAISS 检索"为高层服务：
  输入一张图片路径 → 输出 Top-K 相似文物（含路径 + 相似度）
供后续 Gradio 界面直接调用。
"""
import os
from pathlib import Path

import yaml

from src.features.hybrid import extract_hybrid_feature
from src.kg.query import query_artifact_info
from src.retrieval.faiss_index import search

ROOT = Path(__file__).resolve().parents[2]          # src/retrieval/ -> 项目根


def load_config():
    with open(ROOT / "config" / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class ArtifactSearchService:
    """文物检索服务：封装图片检索 + 图谱查询的核心流程"""

    def __init__(self, config_path=None):
        cfg = load_config() if config_path is None else _load(config_path)
        retr = cfg["retrieval"]
        feat = cfg["features"]
        kg = cfg["kg"]
        self.top_k = retr.get("top_k", 5)
        self.dinov2_model = feat.get("dinov2_model", "facebook/dinov2-base")
        self.clip_model = feat.get("clip_model", "openai/clip-vit-base-patch32")
        self.use_hybrid = feat.get("hybrid", True)
        self.index_path = ROOT / retr["index_path"]
        self.id_map_path = ROOT / retr["id_map_path"]
        self.vecs_path = ROOT / feat.get("feature_file", "data/features/hybrid_features.npy")
        # Rerank：粗筛 Top-N → 高 CLIP 权重精排（实验提升 culture P@5 0.316→0.343）
        self.rerank_top_n = retr.get("rerank_top_n", None)
        self.rerank_wd = retr.get("rerank_wd", 0.2)
        self.rerank_wc = retr.get("rerank_wc", 1.0)
        self.kg_uri = kg["uri"]
        self.kg_user = kg["user"]
        self.kg_password = os.environ.get("NEO4J_PASSWORD", "")

    def search_by_image(self, image_path, top_k=None, with_kg=True):
        """核心入口：图片路径 → Top-K 相似文物（可附带图谱信息）"""
        k = top_k or self.top_k
        # 1. 特征提取（默认混合特征 DINOv2+CLIP；可回退纯 DINOv2）
        if self.use_hybrid:
            vec = extract_hybrid_feature(
                image_path, dinov2_model=self.dinov2_model, clip_model=self.clip_model
            )
        else:
            from src.features.dinov2 import extract_feature
            vec = extract_feature(image_path, model_name=self.dinov2_model)
        # 2. FAISS 检索（启用 Rerank 精排）
        results = search(
            vec, top_k=k,
            index_path=self.index_path, id_map_path=self.id_map_path,
            vecs_path=self.vecs_path,
            top_n=self.rerank_top_n, wd=self.rerank_wd, wc=self.rerank_wc,
        )
        # 3. 图谱查询：为每条结果附带年代/文化
        if with_kg:
            for r in results:
                oid = r["image_path"].split("/")[-1].replace(".jpg", "")
                r["kg"] = query_artifact_info(
                    oid, self.kg_uri, self.kg_user, self.kg_password
                )
        return results


def _load(config_path):
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
