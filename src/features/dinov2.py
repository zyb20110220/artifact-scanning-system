#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DINOv2 特征提取模块（阶段 2 · 任务 2.1）

提供"图片路径 → 768 维 L2 归一化特征向量"的复用函数。
模型只在首次调用时加载，之后复用（避免 Gradio 多次请求重复加载）。
"""
import numpy as np
import torch
from PIL import Image
from transformers import AutoImageProcessor, AutoModel

# 模块级缓存：模型 + 处理器只加载一次
_model = None
_processor = None


def get_model(model_name: str = "facebook/dinov2-base"):
    """加载（或复用）DINOv2 模型与处理器"""
    global _model, _processor
    if _model is None:
        _model = AutoModel.from_pretrained(model_name)
        _model.eval()                       # 推理模式，关闭 dropout
        _processor = AutoImageProcessor.from_pretrained(model_name)
    return _model, _processor


def extract_feature(image_path, model_name: str = "facebook/dinov2-base") -> np.ndarray:
    """
    从单张图片提取 768 维特征向量并做 L2 归一化。
    返回形状为 (768,) 的 float32 numpy 数组。
    """
    model, processor = get_model(model_name)
    img = Image.open(image_path).convert("RGB")     # 统一 RGB，避免灰度/透明报错
    inputs = processor(images=img, return_tensors="pt")
    with torch.no_grad():                           # 推理不计算梯度
        outputs = model(**inputs)
    feature = outputs.last_hidden_state[:, 0].squeeze().numpy()   # 取 CLS token
    return feature / np.linalg.norm(feature)        # L2 归一化
