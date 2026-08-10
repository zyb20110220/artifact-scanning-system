#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
补齐 metadata 缺失的 culture/period/medium 标签（阶段 2 · 检索优化）

背景：MET 关键词搜索返回的详情里约 70% 缺 culture/period（下载阶段字段未全量保存）。
本脚本对缺失标签的 object_id 重新请求 MET 详情 API，把 culture / period / medium / object_date
补回到 data/raw/metadata.csv，提升检索评估与图谱构建的真值质量。

用法（在容器内运行）：
  docker compose run --rm app python scripts/backfill_metadata.py
  docker compose run --rm app python scripts/backfill_metadata.py --only-missing
"""
import argparse
import logging
import time
from pathlib import Path

import pandas as pd
import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "config.yaml"
METADATA_CSV = ROOT / "data" / "raw" / "metadata.csv"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def safe_get(url, retries=3, base_wait=2.0):
    """带指数退避重试的 GET（应对 MET 429/403/SSL 抖动）"""
    for a in range(retries):
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 403:          # 疑似封禁，退避
                time.sleep(base_wait * (2 ** a) + 1)
                continue
            if r.status_code == 429:          # 限流，退避更长
                time.sleep(base_wait * (2 ** a) + 3)
                continue
            r.raise_for_status()
            return r
        except Exception:
            time.sleep(base_wait * (2 ** a))
    return None


def is_blank(v):
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == ""


def main():
    parser = argparse.ArgumentParser(description="补齐 MET 缺失标签")
    parser.add_argument("--only-missing", action="store_true",
                        help="只补缺失项，不覆盖已有值（默认覆盖 culture/period/medium 空值）")
    args = parser.parse_args()

    cfg = load_config()["data"]
    api_base = cfg["met_api_base"]

    df = pd.read_csv(METADATA_CSV)
    # 找缺 culture 或 period 的行（medium 99.9% 齐全，一并兜底）
    mask = df.apply(
        lambda r: is_blank(r.get("culture")) or is_blank(r.get("period")) or is_blank(r.get("medium")),
        axis=1,
    )
    need = df[mask]
    logger.info("需补标签: %d / %d 件", len(need), len(df))

    filled, fail = 0, 0
    for i, idx in enumerate(need.index):
        row = df.loc[idx]
        oid = int(row["object_id"])
        resp = safe_get(f"{api_base}/objects/{oid}")
        if resp is None:
            fail += 1
            continue
        d = resp.json()
        updated = False
        # MET 对这些对象常缺 culture/period，但 objectDate/classification/title 基本齐全
        for col, src in [("culture", "culture"), ("period", "period"),
                         ("object_date", "objectDate"), ("medium", "medium"),
                         ("classification", "classification")]:
            if col not in df.columns:
                df[col] = ""
            raw = d.get(src)
            val = raw.strip() if isinstance(raw, str) else ""
            if val and (args.only_missing or is_blank(df.at[idx, col])):
                df.at[idx, col] = val
                updated = True
        if updated:
            filled += 1
        time.sleep(0.3)                        # 限流控制
        if (i + 1) % 100 == 0:                 # 每 100 件落盘一次，防中断丢失
            logger.info("进度: %d / %d (补全 %d, 失败 %d)", i + 1, len(need), filled, fail)
            df.to_csv(METADATA_CSV, index=False, encoding="utf-8")

    df.to_csv(METADATA_CSV, index=False, encoding="utf-8")
    missing_after = df.apply(
        lambda r: is_blank(r.get("culture")) or is_blank(r.get("period")), axis=1
    ).sum()
    logger.info("完成！补全 %d 件，失败 %d 件；剩余缺 culture/period: %d", filled, fail, missing_after)


if __name__ == "__main__":
    main()
