#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
断代报告 Prompt 模板（阶段 3 · 任务 3.2）

把检索结果组织成"参考信息"文本，与查询图片一起构造多模态 Prompt。
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

SYSTEM_PROMPT = (
    "你是一位资深的考古文物鉴定专家，精通中国及世界古代文物"
    "（陶瓷、青铜、玉器、雕塑等）的年代与类型鉴定。\n"
    "你将看到一张文物图片，以及从数据库中检索到的相似文物参考信息。\n"
    "请基于图片本身的特征（器型、纹饰、材质、工艺风格）和参考信息，"
    "给出专业、谨慎的鉴定结论。\n"
    "如果信息不足以确定，给出合理的年代范围而非精确年份，并说明不确定性。"
)

_metadata_cache = None


def load_metadata():
    """读取 metadata.csv，建立 image_path -> 行 映射（带缓存）"""
    global _metadata_cache
    if _metadata_cache is None:
        df = pd.read_csv(ROOT / "data" / "raw" / "metadata.csv")
        _metadata_cache = {str(r["image_path"]): r for _, r in df.iterrows()}
    return _metadata_cache


def build_retrieval_context(results):
    """
    把检索结果组织成文本上下文（给 LLM 作参考证据链）。
    results: search_by_image 的返回值（含 image_path, score, kg）
    """
    meta = load_metadata()
    lines = []
    for i, r in enumerate(results, 1):
        kg = r.get("kg") or {}
        m = meta.get(r["image_path"], {})
        period = kg.get("period") or m.get("period") or "未知"
        culture = kg.get("culture") or m.get("culture") or "未知"
        medium = m.get("medium") or "未知"
        lines.append(
            f"{i}. 相似度={r['score']:.2f} | 时期={period} | 文化={culture} | 材质={medium}"
        )
    return "\n".join(lines) if lines else "（无参考信息）"


def build_user_text(context: str) -> str:
    """构造用户消息文本（含参考信息 + 输出格式要求）"""
    return f"""请鉴定这张文物图片。

【参考信息：数据库检索到的相似文物】
{context}

【输出格式要求】
请以结构化文本输出：
1. 年代推断：XXXX（置信度：高/中/低）
2. 文物类型与材质
3. 关联相似文物（引用上面参考信息的编号）
4. 判断理由（2-3 条）"""
