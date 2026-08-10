#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
考古文物检索系统 — Gradio 界面（阶段 2 · 任务 2.3）

功能：
  上传文物图片 → 展示相似文物画廊 + 元数据表格（年代/文化）

运行：
  docker compose up app
访问：
  http://localhost:7860
"""
import logging
import sys
from pathlib import Path

import gradio as gr
import pandas as pd

# 确保能 import 项目根下的 src 包（脚本运行时 cwd 是 /app/app）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.retrieval.service import ArtifactSearchService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# 全局单例：模型/索引/驱动只加载一次（首次加载模型约 30-60 秒）
logger.info("加载检索服务（首次约 30-60 秒）...")
service = ArtifactSearchService()
logger.info("检索服务就绪 ✅")


def search_artifacts(image_path):
    """上传图片 → 返回（相似文物图片列表, 元数据表格）"""
    empty_df = pd.DataFrame(columns=["图片", "相似度", "时期", "文化"])
    if image_path is None:
        return None, empty_df

    # 核心调用：检索 + 图谱信息
    results = service.search_by_image(image_path, with_kg=True)

    # 1. 画廊：相似文物图片路径列表
    gallery = [r["image_path"] for r in results]

    # 2. 表格：元数据（含图谱的年代/文化）
    rows = []
    for r in results:
        kg = r.get("kg") or {}
        rows.append({
            "图片": r["image_path"].split("/")[-1],
            "相似度": round(r["score"], 3),
            "时期": kg.get("period") or "",
            "文化": kg.get("culture") or "",
        })
    return gallery, pd.DataFrame(rows)


# ---------- 界面布局 ----------
with gr.Blocks(title="考古文物断代与鉴定系统") as demo:
    gr.Markdown("# 🏛️ 考古文物检索系统")
    gr.Markdown("上传文物图片，系统将检索最相似的文物，并展示其年代与文化信息。")

    with gr.Row():
        # 左列：上传区
        with gr.Column(scale=1):
            image_input = gr.Image(type="filepath", label="上传文物图片")
            search_btn = gr.Button("🔍 检索相似文物", variant="primary")

        # 右列：结果区
        with gr.Column(scale=2):
            gallery_output = gr.Gallery(label="相似文物", columns=4, height=400)
            table_output = gr.DataFrame(label="相似文物信息")

    # 绑定事件：点击按钮 → 执行检索 → 输出到画廊和表格
    search_btn.click(
        fn=search_artifacts,
        inputs=image_input,
        outputs=[gallery_output, table_output],
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
