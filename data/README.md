# data — 数据目录（Git 忽略，DVC 管理）

| 子目录 | 内容 | 阶段 |
|---|---|---|
| `raw/` | 原始图片、元数据 CSV/JSONL | 1 |
| `features/` | 特征向量 (.npy / Parquet) | 1 |
| `kg/` | 知识图谱导入 CSV | 1 |
| `train/` | LoRA 微调数据 | 3 |

> ⚠️ 大文件不入 Git。使用 DVC：`dvc add data/...`。
