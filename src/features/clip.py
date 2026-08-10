#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLIP 特征提取模块（阶段 2 · 检索优化）

提供"图片路径 → 512 维 L2 归一化特征向量"的复用函数。
CLIP 对"文物语义类别"（是什么器物/什么文化）更敏感，与 DINOv2 互补：
  - DINOv2：视觉细节 / 局部纹理（768 维）
  - CLIP：  语义类别对齐（512 维）
两者拼接形成 1280 维混合特征，可显著提升文化 / 时期召回。
模型只在首次调用时加载，之后复用（避免 Gradio 多次请求重复加载）。
"""
import numpy as np
import torch
from PIL import Image
from transformers import CLIPImageProcessor, CLIPModel

# 模块级缓存：模型 + 处理器只加载一次
_model = None
_processor = None


def get_model(model_name: str = "openai/clip-vit-base-patch32"):
    """加载（或复用）CLIP 模型与处理器"""
    global _model, _processor
    if _model is None:
        _model = CLIPModel.from_pretrained(model_name)
        _model.eval()                       # 推理模式，关闭 dropout
        _processor = CLIPImageProcessor.from_pretrained(model_name)
    return _model, _processor


def extract_feature(image_path, model_name: str = "openai/clip-vit-base-patch32") -> np.ndarray:
    """
    从单张图片提取 512 维 CLIP 特征向量并做 L2 归一化。
    返回形状为 (512,) 的 float32 numpy 数组。
    """
    model, processor = get_model(model_name)
    img = Image.open(image_path).convert("RGB")     # 统一 RGB，避免灰度/透明报错
    inputs = processor(images=img, return_tensors="pt")
    with torch.no_grad():                           # 推理不计算梯度
        feature = model.get_image_features(**inputs)
    feature = feature.squeeze().numpy()             # (512,)
    return feature / np.linalg.norm(feature)        # L2 归一化
