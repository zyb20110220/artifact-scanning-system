# 🔁 复现指南（Reproducibility）

> 本文档说明如何**从零开始完整复现**本项目的**数据获取与处理流程**。
> 所有步骤均为**纯软件实现**：数据来自公开 API（MET Open Access、Wikidata SPARQL），**无任何手动标注或人工步骤**。

---

## 1. 环境要求

| 项 | 要求 |
|---|---|
| 容器 | Docker Desktop ≥ 4.x（国内需可访问 Docker Hub，建议配置代理）|
| 磁盘 | 约 5 GB（镜像 + 数据）|
| 内存 | ≥ 8 GB |
| GPU | 可选（本项目按 **CPU 路线**运行）|

---

## 2. 启动环境

```bash
docker compose up -d neo4j       # 启动 Neo4j 数据库
docker compose build             # 构建应用镜像（首次较慢）
```

---

## 3. 复现流程（严格按顺序）

| 步骤 | 命令 | 产出 |
|---|---|---|
| **3.1 下载数据** | `docker compose run --rm app python scripts/download_met.py --max-objects 3000` | `data/raw/`（图片 + metadata.csv）|
| **3.2 提取特征** | `docker compose run --rm app python scripts/extract_features.py` | `data/features/`（parquet + npy + id_map）|
| **3.3 构建索引** | `docker compose run --rm app python scripts/build_index.py` | `data/features/dinov2_hnsw.index` |
| **3.4 构建图谱** | `docker compose run --rm app python scripts/build_kg.py` | Neo4j 知识图谱 |

> 💡 `download_met.py` 的 `--max-objects` 可调；受 MET API 限流影响，实际数量以 API 返回为准。

---

## 4. 可重复性保证

| 机制 | 说明 |
|---|---|
| **断点续传** | 下载脚本记录进度（`download_progress.json`），中断重跑自动跳过已下载 |
| **幂等导入** | 图谱导入用 `MERGE` + 唯一约束，重复执行**不会产生重复节点** |
| **版本锁定** | `requirements.txt` 锁定关键版本（如 `numpy==1.26.4` 兼容 faiss 1.7.4）|
| **数据版本控制** | `data/` 由 **DVC** 管理，`data.dvc` 指针入库，数据本体在 `.dvc/cache` |
| **配置外置** | 所有参数在 `config/config.yaml`，改配置即可调流程，不改代码 |

---

## 5. 数据来源与许可

| 数据源 | 提供内容 | 许可 |
|---|---|---|
| MET Open Access API | 文物图片 + 元数据 | CC0（公有领域）|
| Wikidata SPARQL | 时期/文化实体及时间范围 | CC0 |

---

## 6. 网络注意事项（中国大陆环境）

| 目标 | 处理方式 |
|---|---|
| Docker Hub | 需代理（本项目：`http://127.0.0.1:7897`）|
| HuggingFace 模型 | 容器内经 `HTTP_PROXY=http://host.docker.internal:7897` 访问 |
| MET / Wikidata API | 直连可用 |

---

## 7. 验证复现成功

```bash
# 检查数据
docker compose run --rm app python -c "import numpy as np; a=np.load('/app/data/features/dinov2_features.npy'); print(a.shape)"   # 期望 (N, 768)

# 检查图谱（应显示节点统计）
docker compose run --rm app python scripts/verify_kg.py
```
