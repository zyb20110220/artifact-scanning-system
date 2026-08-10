#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
性能基准测试（阶段 4 · 任务 4.4）

测量各环节耗时（CPU 环境）：
  [1] DINOv2 特征提取
  [2] FAISS 检索 Top-5
  [3] Neo4j 图谱查询
  [4] LLM 断代报告（可选，--with-llm）

运行：
  docker compose run --rm app python scripts/benchmark.py
  docker compose run --rm app python scripts/benchmark.py --with-llm
"""
import argparse
import os
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))          # 确保能 import 项目根的 src 包


def load_config():
    with open(ROOT / "config" / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="性能基准测试")
    parser.add_argument("--image", default="/app/data/raw/images/451320.jpg")
    parser.add_argument("--with-llm", action="store_true", help="包含 LLM 调用耗时")
    args = parser.parse_args()

    cfg = load_config()
    retr, feat, kg = cfg["retrieval"], cfg["features"], cfg["kg"]

    from src.features.dinov2 import extract_feature
    from src.kg.query import query_artifact_info
    from src.retrieval.faiss_index import search

    print("=" * 50)
    print("性能基准测试（CPU 环境）")
    print("=" * 50)

    # [1] DINOv2 特征提取（首次，含模型加载）
    t0 = time.time()
    vec = extract_feature(args.image, model_name=feat["dinov2_model"])
    t1 = time.time()
    print(f"[1] DINOv2 特征提取(首次) : {t1 - t0:6.2f}s")

    # [1b] 预热后的特征提取（模型已加载，纯推理耗时 = 实际单次查询）
    t1b0 = time.time()
    extract_feature(args.image, model_name=feat["dinov2_model"])
    t1b1 = time.time()
    print(f"[1b] 特征提取(模型已加载) : {t1b1 - t1b0:6.2f}s")

    # [2] FAISS 检索
    t2 = time.time()
    results = search(vec, 5,
                     index_path=ROOT / retr["index_path"],
                     id_map_path=ROOT / retr["id_map_path"])
    t3 = time.time()
    print(f"[2] FAISS 检索 Top-5   : {t3 - t2:6.3f}s")

    # [3] Neo4j 图谱查询（5 件）
    t4 = time.time()
    password = os.environ.get("NEO4J_PASSWORD", "")
    for r in results:
        oid = r["image_path"].split("/")[-1].replace(".jpg", "")
        query_artifact_info(oid, kg["uri"], kg["user"], password)
    t5 = time.time()
    print(f"[3] Neo4j 图谱查询(5件): {t5 - t4:6.3f}s")

    # [4] LLM（可选）
    llm_time = 0.0
    if args.with_llm:
        from src.llm.service import LLMReportService
        svc = LLMReportService()
        t6 = time.time()
        svc.generate_report(args.image, results)
        t7 = time.time()
        llm_time = t7 - t6
        print(f"[4] LLM 断代报告       : {llm_time:6.2f}s")

    print("-" * 50)
    total = (t5 - t0) if not args.with_llm else (t5 - t0) + llm_time
    print(f"总耗时（含 LLM）: {total:.2f}s")
    print(f"  其中 检索+图谱（不含特征/LLM）: {t5 - t1:.3f}s")


if __name__ == "__main__":
    main()
