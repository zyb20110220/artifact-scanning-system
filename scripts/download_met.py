#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MET Museum 数据下载脚本（阶段 1 · 任务 1.2）

功能：
  1. 按部门（departmentIds）获取古代文物 objectID 列表
  2. 逐个请求详情，过滤「有图 + 目标材质」的文物
  3. 下载图片（统一 JPEG，最长边 1024px，EXIF 修正）
  4. 元数据保存为 CSV
  5. 支持断点续传（崩溃后重跑自动跳过已下载）

用法（在容器内运行）：
  docker compose run --rm app python scripts/download_met.py
  docker compose run --rm app python scripts/download_met.py --max-objects 100
"""

import argparse
import io
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests
import yaml
from PIL import Image, ImageOps
from tqdm import tqdm

# ---------- 路径（脚本在 scripts/ 下，项目根在上一级） ----------
ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "config.yaml"
DATA_DIR = ROOT / "data" / "raw"
IMAGES_DIR = DATA_DIR / "images"
METADATA_CSV = DATA_DIR / "metadata.csv"
PROGRESS_JSON = DATA_DIR / "download_progress.json"

# ---------- 日志 ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def load_config():
    """读取全局配置 config.yaml"""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_object_ids_by_search(api_base, keywords):
    """
    方案 B：按关键词搜索获取 objectID 列表。
    search?q=<kw>&hasImages=true 返回的已是匹配关键词且有图的文物，
    请求量远小于部门全量枚举，不易触发限流。
    """
    ids = []
    for kw in keywords:
        url = f"{api_base}/search?q={kw}&hasImages=true"
        resp = requests.get(url, timeout=30)
        if resp.status_code == 403:
            logger.error("MET 返回 403（限流/封禁）：请稍后再试，或申请 MET API Key")
            raise SystemExit(1)
        resp.raise_for_status()
        data = resp.json()
        kw_ids = data.get("objectIDs", []) or []
        logger.info("关键词 %s: %d 个对象", kw, len(kw_ids))
        ids.extend(kw_ids)
        time.sleep(0.5)   # 温和请求
    # 去重并保持顺序
    return list(dict.fromkeys(ids))


def get_object_ids_by_department(api_base, department_ids):
    """
    方案 A：按部门获取全部 objectID 列表（覆盖广，但请求量大）。
    /objects?departmentIds=X 返回该部门所有对象（含无图的）。
    """
    ids = []
    for dept in department_ids:
        url = f"{api_base}/objects?departmentIds={dept}"
        resp = requests.get(url, timeout=30)
        if resp.status_code == 403:
            logger.error("MET 返回 403（限流/封禁）：请等待一段时间后再试，或申请 MET API Key")
            raise SystemExit(1)
        resp.raise_for_status()
        data = resp.json()
        dept_ids = data.get("objectIDs", []) or []
        logger.info("部门 %s: %d 个对象", dept, len(dept_ids))
        ids.extend(dept_ids)
        time.sleep(1.0)   # 温和请求，避免封禁
    # 去重并保持顺序
    return list(dict.fromkeys(ids))


def is_target(detail, medium_keywords):
    """
    判断是否目标文物：
      - 必须有主图（primaryImage 或 primaryImageSmall 非空）
    注：方案 B 中 search 已按关键词过滤，这里只需保证有图；
        方案 A（部门枚举）时 medium_keywords 用于材质过滤。
    """
    if not detail.get("primaryImage") and not detail.get("primaryImageSmall"):
        return False
    medium = (detail.get("medium") or "").lower()
    if medium_keywords:
        return any(kw.lower() in medium for kw in medium_keywords)
    return True


def download_image(detail, save_dir, max_side):
    """
    下载文物图片：EXIF 修正旋转 → 缩放最长边 max_side → 存 JPEG。
    返回图片保存路径，失败返回 None。
    """
    object_id = detail.get("objectID")
    # 优先小图（省带宽），回退原图
    url = detail.get("primaryImageSmall") or detail.get("primaryImage")
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content))
        img = ImageOps.exif_transpose(img)   # 按 EXIF 修正手机/相机旋转
        img.thumbnail((max_side, max_side), Image.LANCZOS)
        img = img.convert("RGB")
        save_dir.mkdir(parents=True, exist_ok=True)
        path = save_dir / f"{object_id}.jpg"
        img.save(path, "JPEG", quality=90)
        return str(path)
    except Exception as e:
        logger.warning("图片下载失败 objectID=%s: %s", object_id, e)
        return None


def process_one(oid, api_base, medium_keywords, save_dir, max_side, stop_event):
    """
    并发 worker：处理单个 objectID → 拉详情 → 过滤 → 下载。
    返回 (status, record)：status ∈ {"ok", "skip", "rate_limit", "error"}
    """
    if stop_event.is_set():          # 已达成目标数量，跳过剩余任务
        return ("skip", None)

    resp = None
    detail = None
    for attempt in range(3):         # 429 限流时最多重试 3 次
        try:
            time.sleep(0.3)          # 请求间隔，控制请求速率（避免封禁）
            resp = requests.get(f"{api_base}/objects/{oid}", timeout=30)
            if resp.status_code == 403:
                return ("rate_limit", None)   # IP 被封，立即标记限流
            if resp.status_code == 429:
                time.sleep(5)
                continue
            resp.raise_for_status()
            detail = resp.json()
            break
        except Exception:
            time.sleep(1)

    if detail is None:
        status = "rate_limit" if resp is not None and resp.status_code == 429 else "error"
        return (status, None)

    if not is_target(detail, medium_keywords):
        return ("skip", None)
    img_path = download_image(detail, save_dir, max_side)
    if img_path is None:
        return ("error", None)
    return ("ok", {
        "object_id": oid,
        "image_path": img_path,
        "title": detail.get("title", ""),
        "culture": detail.get("culture", ""),
        "period": detail.get("period", ""),
        "medium": detail.get("medium", ""),
        "object_date": detail.get("objectDate", ""),
        "object_url": detail.get("objectURL", ""),
    })


def load_progress():
    """读取已下载的 objectID 集合（断点续传）"""
    if PROGRESS_JSON.exists():
        return set(json.loads(PROGRESS_JSON.read_text(encoding="utf-8"))["downloaded"])
    return set()


def save_progress(done):
    """保存已下载的 objectID 集合"""
    PROGRESS_JSON.write_text(
        json.dumps({"downloaded": sorted(done)}), encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser(description="MET 数据下载")
    parser.add_argument(
        "--max-objects", type=int, default=None,
        help="覆盖 config 的采集上限（建议先小规模测试，如 100）",
    )
    parser.add_argument(
        "--threads", type=int, default=4,
        help="并发线程数（默认 4，避免触发 MET 限流；被封禁后调小）",
    )
    args = parser.parse_args()

    cfg = load_config()["data"]
    max_objects = args.max_objects or cfg.get("max_objects", 50000)
    threads = args.threads
    department_ids = cfg.get("department_ids", [6, 12, 13])
    search_keywords = cfg.get("search_keywords", [])
    medium_keywords = cfg.get("medium_keywords", [])
    max_side = cfg.get("image_max_side", 1024)
    api_base = cfg["met_api_base"]

    # 1. 收集候选 objectID（优先方案 B 关键词搜索，请求量小）
    logger.info("获取 objectID 列表...")
    if search_keywords:
        logger.info("使用方案 B：关键词搜索（请求量小，不易限流）")
        object_ids = get_object_ids_by_search(api_base, search_keywords)
        medium_keywords = []   # search 已过滤，无需再按材质过滤
    else:
        logger.info("使用方案 A：部门全量枚举（覆盖广，请求量大）")
        object_ids = get_object_ids_by_department(api_base, department_ids)
    logger.info("共 %d 个候选对象", len(object_ids))

    # 2. 断点续传：跳过已下载的
    done = load_progress()
    todo = [oid for oid in object_ids if oid not in done]
    if not todo:
        logger.info("所有候选对象均已下载，无需继续")
        return

    # 3. 读取已有元数据（续传时在其后追加）
    df_existing = (
        pd.read_csv(METADATA_CSV) if METADATA_CSV.exists() else pd.DataFrame()
    )

    records = []
    stop_event = threading.Event()
    save_lock = threading.Lock()
    stats = {"ok": 0, "skip": 0, "rate_limit": 0, "error": 0}
    logger.info("开始并发下载（上限 %d 件，线程 %d，待处理 %d 件）...", max_objects, threads, len(todo))

    BATCH = threads * 2   # 每批提交的任务数
    with ThreadPoolExecutor(max_workers=threads) as executor:
        for start in range(0, len(todo), BATCH):
            if stop_event.is_set():
                break
            batch = todo[start:start + BATCH]
            futures = [
                executor.submit(
                    process_one, oid, api_base, medium_keywords, IMAGES_DIR, max_side, stop_event
                )
                for oid in batch
            ]
            for fut in as_completed(futures):
                status, record = fut.result()
                stats[status] += 1
                if record:
                    with save_lock:
                        records.append(record)
                        done.add(record["object_id"])
                        if len(done) >= max_objects:
                            stop_event.set()   # 通知其余任务停止

                scanned = sum(stats.values())
                # 心跳：每 300 个候选打印一次推进情况（观察命中率/是否被限流）
                if scanned % 300 == 0:
                    logger.info(
                        "心跳: 扫描 %d | 命中 %d | 跳过 %d | 限流 %d | 错误 %d | 图片 %d",
                        scanned, stats["ok"], stats["skip"], stats["rate_limit"], stats["error"], len(done),
                    )
                # 每 50 件落盘一次进度与 CSV（防意外中断丢失）
                with save_lock:
                    if 0 < len(records) % 50 == 0:
                        save_progress(done)
                        df_new = pd.DataFrame(records)
                        pd.concat([df_existing, df_new], ignore_index=True).to_csv(
                            METADATA_CSV, index=False, encoding="utf-8"
                        )

    # 收尾保存
    save_progress(done)
    if records:
        df_new = pd.DataFrame(records)
        df_all = pd.concat([df_existing, df_new], ignore_index=True)
        df_all.to_csv(METADATA_CSV, index=False, encoding="utf-8")
        logger.info("完成！本次新增 %d 件，累计 %d 件 → %s", len(records), len(df_all), METADATA_CSV)
    else:
        logger.info("本次未新增记录（可能被过滤或无符合条件对象），已有累计记录见 %s", METADATA_CSV)


if __name__ == "__main__":
    main()
