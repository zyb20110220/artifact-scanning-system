#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
混合特征模块（阶段 2 · 检索优化）

拼接 DINOv2(768) + CLIP(512) 为 1280 维混合特征并整体 L2 归一化：
  - DINOv2 特征捕获视觉细节（纹饰、器型局部）
  - CLIP 特征捕获语义类别（器物种类、文化属性）
混合特征同时保留两类信息，检索时文化 / 时期召回显著优于单一 DINOv2。
"""
import numpy as np

from src.features.clip import extract_feature as extract_clip
from src.features.dinov2 import extract_feature as extract_dinov2


def extract_hybrid_feature(
    image_path,
    dinov2_model: str = "facebook/dinov2-base",
    clip_model: str = "openai/clip-vit-base-patch32",
) -> np.ndarray:
    """
    从单张图片提取 1280 维混合特征（DINOv2 + CLIP 拼接，整体 L2 归一化）。
    返回形状为 (1280,) 的 float32 numpy 数组。
    """
    d = extract_dinov2(image_path, model_name=dinov2_model)   # (768,)
    c = extract_clip(image_path, model_name=clip_model)       # (512,)
    h = np.concatenate([d, c])                                # (1280,)
    return h / np.linalg.norm(h)                              # 整体 L2 归一化
