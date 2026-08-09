#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DINOv2 特征提取脚本（阶段 1 · 任务 1.3）

功能：
  1. 读取 metadata.csv 中的图片路径列表
  2. 用 DINOv2 批量提取 768 维特征
  3. 做 L2 归一化（为后续 FAISS 余弦相似度检索做准备）
  4. 保存为 Parquet + npy + id_map（便于阶段 2 构建索引）

用法（在容器内运行）：
  docker compose run --rm app python scripts/extract_features.py
  docker compose run --rm app python scripts/extract_features.py --batch-size 8
"""

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import yaml
from PIL import Image
from tqdm import tqdm
from transformers import AutoImageProcessor, AutoModel

# ---------- 路径 ----------
ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "config.yaml"
METADATA_CSV = ROOT / "data" / "raw" / "metadata.csv"
FEATURE_DIR = ROOT / "data" / "features"

# ---------- 日志 ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def load_config():
    """读取全局配置 config.yaml"""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def extract_features(model, processor, image_paths, batch_size):
    """
    批量提取特征：
      图片 → 预处理 → 前向传播 → 取 [CLS] token（第 0 个位置）
    返回 (N, 768) 的 numpy 数组。
    """
    features = []
    for i in range(0, len(image_paths), batch_size):
        batch_paths = image_paths[i:i + batch_size]
        # 打开并转 RGB（灰度/透明通道会导致报错）
        images = [Image.open(p).convert("RGB") for p in batch_paths]
        inputs = processor(images=images, return_tensors="pt")
        with torch.no_grad():                # 推理模式，不计算梯度，省内存
            outputs = model(**inputs)
        batch_feat = outputs.last_hidden_state[:, 0]   # (B, 768) 取 CLS
        features.append(batch_feat.cpu().numpy())
    return np.concatenate(features, axis=0)


def main():
    parser = argparse.ArgumentParser(description="DINOv2 特征提取")
    parser.add_argument("--batch-size", type=int, default=None, help="覆盖 config 的 batch_size")
    args = parser.parse_args()

    cfg = load_config()["features"]
    model_name = cfg.get("dinov2_model", "facebook/dinov2-base")
    batch_size = args.batch_size or cfg.get("batch_size", 16)

    # 1. 读取元数据，取图片路径列表
    df = pd.read_csv(METADATA_CSV)
    image_paths = df["image_path"].tolist()
    logger.info("待提取图片: %d 张", len(image_paths))

    # 2. 加载模型 + 处理器
    logger.info("加载模型 %s ...", model_name)
    model = AutoModel.from_pretrained(model_name)
    model.eval()
    processor = AutoImageProcessor.from_pretrained(model_name)

    # 3. 批量提取特征
    logger.info("开始提取特征（batch_size=%d）...", batch_size)
    features = extract_features(model, processor, image_paths, batch_size)
    logger.info("原始特征矩阵: %s", features.shape)

    # 4. L2 归一化（把向量长度归一为 1，后续余弦相似度 = 点积）
    features = features / np.linalg.norm(features, axis=1, keepdims=True)
    logger.info("L2 归一化完成")

    # 5. 保存（Parquet + npy + id_map）
    FEATURE_DIR.mkdir(parents=True, exist_ok=True)
    df_out = pd.DataFrame({
        "image_path": image_paths,
        "feature": [f.tolist() for f in features],   # 每行 768 维列表
    })
    df_out.to_parquet(FEATURE_DIR / "dinov2_features.parquet", index=False)
    np.save(FEATURE_DIR / "dinov2_features.npy", features)
    with open(FEATURE_DIR / "id_map.json", "w", encoding="utf-8") as f:
        json.dump(image_paths, f, ensure_ascii=False)

    logger.info("完成！输出 → %s", FEATURE_DIR)
    logger.info("  - dinov2_features.parquet (含 image_path + feature)")
    logger.info("  - dinov2_features.npy     (N, 768)")
    logger.info("  - id_map.json             (N 个 image_path)")


if __name__ == "__main__":
    main()
