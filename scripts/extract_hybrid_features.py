#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
混合特征批量提取脚本（阶段 2 · 检索优化）

同时用 DINOv2(768) + CLIP(512) 提取每张图的特征，拼接为 1280 维并整体 L2 归一化，
保存为 Parquet + npy + id_map，供 FAISS 建混合索引。

用法（在容器内运行）：
  docker compose run --rm app python scripts/extract_hybrid_features.py
  docker compose run --rm app python scripts/extract_hybrid_features.py --batch-size 8
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
from transformers import AutoImageProcessor, AutoModel, CLIPImageProcessor, CLIPModel

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


def extract_hybrid_batch(d_model, d_processor, c_model, c_processor, image_paths, batch_size):
    """
    批量提取混合特征：
      每批图片 → DINOv2 前向 (B,768) + CLIP 前向 (B,512) → 拼接 (B,1280)
    返回 (N, 1280) 的 numpy 数组。
    """
    feats = []
    for i in range(0, len(image_paths), batch_size):
        batch_paths = image_paths[i:i + batch_size]
        # 打开并转 RGB（灰度/透明通道会导致报错）
        images = [Image.open(p).convert("RGB") for p in batch_paths]
        # DINOv2：取 CLS token（第 0 个位置）
        d_inputs = d_processor(images=images, return_tensors="pt")
        with torch.no_grad():
            d_out = d_model(**d_inputs).last_hidden_state[:, 0]      # (B, 768)
        # CLIP：图像特征
        c_inputs = c_processor(images=images, return_tensors="pt")
        with torch.no_grad():
            c_out = c_model.get_image_features(**c_inputs)           # (B, 512)
        h = torch.cat([d_out, c_out], dim=-1).cpu().numpy()          # (B, 1280)
        feats.append(h)
    return np.concatenate(feats, axis=0)


def main():
    parser = argparse.ArgumentParser(description="DINOv2 + CLIP 混合特征提取")
    parser.add_argument("--batch-size", type=int, default=None, help="覆盖 config 的 batch_size")
    args = parser.parse_args()

    cfg = load_config()["features"]
    dinov2_name = cfg.get("dinov2_model", "facebook/dinov2-base")
    clip_name = cfg.get("clip_model", "openai/clip-vit-base-patch32")
    batch_size = args.batch_size or cfg.get("batch_size", 16)

    # 1. 读取元数据，取图片路径列表
    df = pd.read_csv(METADATA_CSV)
    image_paths = df["image_path"].tolist()
    logger.info("待提取图片: %d 张", len(image_paths))

    # 2. 加载两个模型
    logger.info("加载 DINOv2 %s ...", dinov2_name)
    d_model = AutoModel.from_pretrained(dinov2_name)
    d_model.eval()
    d_processor = AutoImageProcessor.from_pretrained(dinov2_name)

    logger.info("加载 CLIP %s ...", clip_name)
    c_model = CLIPModel.from_pretrained(clip_name)
    c_model.eval()
    c_processor = CLIPImageProcessor.from_pretrained(clip_name)

    # 3. 批量提取混合特征
    logger.info("开始提取混合特征（batch_size=%d）...", batch_size)
    features = extract_hybrid_batch(d_model, d_processor, c_model, c_processor, image_paths, batch_size)
    logger.info("原始特征矩阵: %s", features.shape)

    # 4. 整体 L2 归一化（DINOv2/CLIP 各自归一化后拼接，再整体归一化）
    features = features / np.linalg.norm(features, axis=1, keepdims=True)
    logger.info("L2 归一化完成")

    # 5. 保存（Parquet + npy + id_map）
    FEATURE_DIR.mkdir(parents=True, exist_ok=True)
    df_out = pd.DataFrame({
        "image_path": image_paths,
        "feature": [f.tolist() for f in features],   # 每行 1280 维列表
    })
    df_out.to_parquet(FEATURE_DIR / "hybrid_features.parquet", index=False)
    np.save(FEATURE_DIR / "hybrid_features.npy", features)
    with open(FEATURE_DIR / "id_map.json", "w", encoding="utf-8") as f:
        json.dump(image_paths, f, ensure_ascii=False)

    logger.info("完成！输出 → %s", FEATURE_DIR)
    logger.info("  - hybrid_features.parquet (含 image_path + feature)")
    logger.info("  - hybrid_features.npy     (N, 1280)")
    logger.info("  - id_map.json             (N 个 image_path)")


if __name__ == "__main__":
    main()
