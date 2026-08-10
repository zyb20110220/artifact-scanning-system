#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM 断代报告服务（阶段 3 · 任务 3.3）

组合"检索结果 + Qwen-VL API"生成结构化断代报告：
  图片 → 检索 Top-5 → 组织参考上下文 → 调 Qwen-VL → 返回报告
"""
import os
from pathlib import Path

import yaml

from src.llm.client import chat_with_image
from src.llm.report import SYSTEM_PROMPT, build_retrieval_context, build_user_text

ROOT = Path(__file__).resolve().parents[2]


def load_config():
    with open(ROOT / "config" / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class LLMReportService:
    """LLM 断代报告服务（云端 Qwen-VL）"""

    def __init__(self, config_path=None):
        cfg = load_config() if config_path is None else _load(config_path)
        llm = cfg["llm"]
        self.api_base = llm["api_base"]
        key_env = llm.get("api_key_env", "QWEN_API_KEY")
        self.api_key = os.environ.get(key_env, "")
        self.model = llm.get("model", "qwen-vl-max")
        self.max_tokens = llm.get("max_new_tokens", 1024)
        self.temperature = llm.get("temperature", 0.3)
        if not self.api_key:
            raise ValueError(f"未找到 API Key：环境变量 {key_env} 为空")

    def generate_report(self, image_path, search_results):
        """图片 + 检索结果 → 断代报告文本"""
        context = build_retrieval_context(search_results)   # 证据链文本
        user_text = build_user_text(context)                # 用户消息
        return chat_with_image(
            self.api_base, self.api_key, self.model,
            SYSTEM_PROMPT, image_path, user_text,
            max_tokens=self.max_tokens, temperature=self.temperature,
        )


def _load(config_path):
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
