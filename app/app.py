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

from src.llm.service import LLMReportService
from src.retrieval.service import ArtifactSearchService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# 全局单例：检索服务（模型/索引/驱动只加载一次）
logger.info("加载检索服务（首次约 30-60 秒）...")
service = ArtifactSearchService()
logger.info("检索服务就绪 ✅")

# 全局单例：LLM 报告服务（云端 API）
try:
    report_service = LLMReportService()
    logger.info("LLM 报告服务就绪 ✅")
except Exception as e:
    logger.warning("LLM 服务不可用（检查 QWEN_API_KEY）: %s", e)
    report_service = None


def search_artifacts(image_path):
    """上传图片 → 返回（画廊, 表格, 检索状态）"""
    empty_df = pd.DataFrame(columns=["图片", "相似度", "时期", "文化"])
    if image_path is None:
        return None, empty_df, None

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
    # 3. 返回检索状态（查询图 + 结果），供"生成报告"按钮使用
    return gallery, pd.DataFrame(rows), (image_path, results)


def generate_report(state):
    """基于检索结果生成 LLM 断代报告"""
    if report_service is None:
        return "⚠️ LLM 服务未配置：请检查 .env 中的 QWEN_API_KEY"
    if state is None:
        return "请先上传图片并点击『检索相似文物』"
    image_path, results = state
    try:
        return report_service.generate_report(image_path, results)
    except Exception as e:
        logger.error("报告生成失败: %s", e)
        return f"⚠️ 报告生成失败：{e}"


# ---------- 界面布局 ----------
with gr.Blocks(title="考古文物断代与鉴定系统") as demo:
    gr.Markdown("# 🏛️ 考古文物检索系统")
    gr.Markdown("上传文物图片，系统将检索最相似的文物，并展示其年代与文化信息。")

    # 保存检索状态（查询图 + 检索结果）
    search_state = gr.State(None)

    with gr.Row():
        # 左列：上传区
        with gr.Column(scale=1):
            image_input = gr.Image(type="filepath", label="上传文物图片")
            search_btn = gr.Button("🔍 检索相似文物", variant="primary")
            report_btn = gr.Button("📝 生成鉴定报告", variant="secondary")

        # 右列：结果区
        with gr.Column(scale=2):
            gallery_output = gr.Gallery(label="相似文物", columns=4, height=400)
            table_output = gr.DataFrame(label="相似文物信息")

    report_output = gr.Textbox(label="鉴定报告（LLM）", lines=15)

    # 事件绑定：检索 → 画廊+表格+状态；生成报告 → LLM 输出
    search_btn.click(
        fn=search_artifacts,
        inputs=image_input,
        outputs=[gallery_output, table_output, search_state],
    )
    report_btn.click(
        fn=generate_report,
        inputs=search_state,
        outputs=report_output,
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
