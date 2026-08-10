#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Qwen-VL 云端 API 客户端（阶段 3 · 任务 3.1）

使用 OpenAI 兼容接口调用阿里百炼（DashScope）的多模态模型 qwen-vl-max。
无 GPU 方案：图片 base64 编码 + 文本一起发送，模型返回鉴定文本。
"""
import base64
import io
import logging

import requests
from PIL import Image

logger = logging.getLogger(__name__)


def encode_image_base64(image_path: str, max_side: int = 1024) -> str:
    """
    把图片统一转为 JPEG 并 base64 编码。
    原因：Gradio 上传的图可能是 PNG 等格式，统一转 JPEG 保证
    data URL 的 MIME 正确（避免 API 400），并缩放控制 payload 大小。
    """
    img = Image.open(image_path).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def chat_with_image(
    api_base: str,
    api_key: str,
    model: str,
    system_prompt: str,
    image_path: str,
    user_text: str,
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> str:
    """
    发送多模态消息（图片 + 文本）给 Qwen-VL，返回文本回复。

    参数：
      api_base      OpenAI 兼容端点，如 https://dashscope.aliyuncs.com/compatible-mode/v1
      api_key       阿里百炼 API Key
      model         模型名，如 qwen-vl-max / qwen-vl-plus
      system_prompt 系统角色设定
      image_path    查询图片路径
      user_text     用户文本（含检索到的参考信息）
    """
    b64 = encode_image_base64(image_path)
    url = f"{api_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    # 图片用 data URL 形式内联（base64）
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": user_text},
                ],
            },
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    logger.info("调用 Qwen-VL: model=%s image=%s", model, image_path.split("/")[-1])
    resp = requests.post(url, headers=headers, json=payload, timeout=180)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]
