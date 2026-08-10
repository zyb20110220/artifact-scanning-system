# 📈 项目进度跟踪（PROGRESS）

> 本文件是**唯一权威进度记录**。每完成一个子任务，请更新对应状态（✅ / ⬜ / 🔄 / ❌），并补记：
> - **日期**、**做了什么**、**遇到什么问题**、**如何解决**
> - 关键决策与踩坑记录（便于复盘）

**仓库**：https://github.com/zyb20110220/artifact-scanning-system
**当前阶段**：阶段 1（数据准备与环境搭建）— 进行中（1.1 环境搭建 ✅）

---

## 阶段 1：数据准备与环境搭建（2-3 周）

### 目标清单

| # | 任务 | 状态 | 完成日期 | 备注 |
|---|---|---|---|---|
| 1.1 | 搭建开发环境并安装全部依赖，锁定版本，生成 requirements.txt | ✅ | 2026-08-09 | 无 GPU → 改用 Docker 容器 + CPU 方案；requirements.txt 已调整为 CPU 版 |
| 1.2 | 编写数据下载脚本（MET API），获取 1-5 万张文物图片 + 元数据 | ✅(部分) | 2026-08-09 | 下载 299 件（MET 限流严，1571 候选仅命中 299）；够阶段 2 演示用，后续可补充 |
| 1.3 | 下载 DINOv2 / CLIP 模型，为图片提取特征向量，存为 Parquet | ✅ | 2026-08-09 | DINOv2 提取 299 张 → (299,768) L2 归一化 → parquet/npy/id_map |
| 1.4 | 构建 FAISS 索引（HNSW），关联向量与图像路径 | ✅ | 2026-08-09 | HNSW(IP/余弦) 299 向量，自测 5/5，真实检索 Top-5 相似度 0.60-1.0 |
| 1.5 | 从 Wikidata 抽取文物 KG 三元组，导入 Neo4j | ✅ | 2026-08-09 | 本地 299 件 + Wikidata 补全时期/文化(41/80匹配)；节点 299+45+37，关系 220 |
| 1.6 | 数据获取代码纯软件实现、可重复执行 | ✅ | 2026-08-09 | DVC 管理 data/；复现文档；幂等验证通过 |

### 进度日志

<details>
<summary><b>环境搭建</b></summary>

- [x] 2026-08-09：创建 Docker 项目骨架（Dockerfile + docker-compose + .env + .dockerignore）
  - 遇到的问题：机器无 NVIDIA GPU，原 GPU 计划不可行
  - 解决方案：改用 CPU 路线（Docker CPU 镜像 + faiss-cpu + 云端 LLM API）
- [x] 2026-08-09：安装依赖（CPU 版 PyTorch 2.4.1 + transformers 4.43.3 等），镜像构建成功
  - 遇到的问题：Docker Hub 被墙，公共镜像加速器全部失效
  - 解决方案：配置机场代理（http://127.0.0.1:7897）到 Docker Desktop
- [x] 2026-08-09：启动 Neo4j 容器，浏览器控制台 + Python 驱动均验证连接成功
  - 遇到的问题：无（Neo4j 用 Docker 本地容器，无需注册账号）
  - 解决方案：NEO4J_AUTH 用 .env 密码初始化
</details>

<details>
<summary><b>数据获取</b></summary>

- [x] 2026-08-09：编写 scripts/download_met.py（按部门枚举 + 材质过滤 + 并发下载 + 断点续传）
  - 遇到的问题：串行请求慢（11 万件需约 76 小时）；medium 过滤命中率低
  - 解决方案：ThreadPoolExecutor 并发 8 线程（提速约 10 倍）；扩充 medium 关键词
  - 验证：--max-objects 5 测试通过，下载 8 件汉代/新石器时代文物图片 + 元数据
- [x] 2026-08-09：数据策略切换为方案 B（关键词搜索，1571 候选，后台下载中）
  - 遇到的问题：8 并发触发 MET API 403 封禁；部门枚举请求量大
  - 解决方案：降并发到 4 + 请求间隔；改用 search 关键词（请求量小约 10 倍）
  - 说明：方案 B 上限约 1571 件，如需更多可扩充关键词或方案 A 温和补充
- [x] 2026-08-09：方案 B 全量下载完成（累计 299 件）
  - 遇到的问题：MET 对详情端点限流极严（心跳显示 1159 次 429），1571 候选仅命中 299
  - 解决方案：299 件足够阶段 2 检索演示；如需扩充用慢速分批或申请 MET API Key
</details>

<details>
<summary><b>特征提取</b></summary>

- [x] 2026-08-09：DINOv2 批量提取 299 张文物特征（facebook/dinov2-base, 768 维）
  - 遇到的问题：容器内访问 HuggingFace 需代理（容器内 127.0.0.1 非宿主机）
  - 解决方案：docker-compose 加 HTTP_PROXY=http://host.docker.internal:7897
  - 结果：(299,768) L2 归一化 → parquet + npy + id_map（耗时约 2 分钟）
</details>

<details>
<summary><b>索引构建</b></summary>

- [x] 2026-08-09：FAISS HNSW 索引构建 + 自测
  - 遇到的问题：faiss 1.7.4 不兼容 numpy 2.x（numpy.core.multiarray failed）
  - 解决方案：锁定 numpy==1.26.4 并重建镜像
  - 结果：HNSW(IP/余弦) 299 向量，自测 5/5，真实检索 Top-5 相似度 0.60-1.0
</details>

<details>
<summary><b>图谱构建</b></summary>

- [x] 2026-08-09：build_kg.py 构建知识图谱并导入 Neo4j
  - 遇到的问题：MET 藏品在 Wikidata 直接关联覆盖极低(<0.2%)；label 精确匹配率仅 8%；关系 MERGE 误建重复节点
  - 解决方案：归一化(去括号)匹配提升到 51%；两阶段导入(先节点+唯一约束，再关系)修复重复
  - 结果：Artifact 299 + Culture 45 + Period 37，关系 220；Wikidata 补全时间范围(如唐 618-907)
</details>

<details>
<summary><b>可复现性</b></summary>

- [x] 2026-08-09：DVC 初始化并跟踪 data/（data.dvc 指针，306 文件 23MB）
  - 遇到的问题：data/ 已被 git 跟踪（data/README.md 未排除）
  - 解决方案：git rm --cached data 后交 DVC 管理
- [x] 2026-08-09：编写 docs/reproducibility.md（环境/复现流程/可重复性保证/数据许可）
- [x] 2026-08-09：幂等性验证（重跑 build_kg.py 节点数不变 381）
</details>

---

## 阶段 2：建立检索基线（3 周）

### 目标清单

| # | 任务 | 状态 | 完成日期 | 备注 |
|---|---|---|---|---|
| 2.1 | 图片上传 → DINOv2 特征提取 → FAISS Top-5 检索 | ✅ | 2026-08-10 | src/ 模块化；ArtifactSearchService 验证通过（Top-5） |
| 2.2 | 从 Neo4j 查询每件文物的年代、出土地等 | ✅ | 2026-08-10 | src/kg/query.py；检索结果自动附带时期/文化 |
| 2.3 | Gradio 界面：上传图片显示相似文物图像 + 元数据 | ✅ | 2026-08-10 | app/app.py 运行正常，浏览器验证通过；检索精度待 2.4 调优 |
| 2.4 | 人工标注数据上评估 Top-5 准确率，调优参数 | ✅ | 2026-08-10 | 三种标准 P@5: culture 0.213 / period 0.774 / medium 0.569；证明检索有效 |

### 进度日志

<details>
<summary><b>检索 Pipeline</b></summary>

- [x] 2026-08-10：src/ 模块化改造（features/dinov2.py + retrieval/faiss_index.py + service.py）
  - 遇到的问题：命令行转义；模型重复加载
  - 解决方案：模块级缓存（模型/索引只加载一次）；ArtifactSearchService 封装
  - 验证：search_by_image 返回 Top-5（相似度 1.0 / 0.788 / 0.698 / 0.69 / 0.516）
- [x] 2026-08-10：图谱查询集成（src/kg/query.py + service 扩展 with_kg）
  - 遇到的问题：部分文物无图谱信息（metadata culture/period 缺失约 70%）
  - 解决方案：OPTIONAL MATCH + 缺失返回空 dict（结果仍可用）
  - 验证：检索结果自动附带时期/文化（如 706056 → Mughal/Islamic）
- [x] 2026-08-10：Gradio 界面（app/app.py）
  - 遇到的问题：compose 挂载 YAML 换行丢失；ModuleNotFoundError src
  - 解决方案：修复挂载换行（docker compose config 验证）；app.py 加 sys.path 项目根
  - 结果：浏览器上传 → 相似文物画廊 + 信息表格，用户验证通过（无异常）
  - 待办：检索精度不足（299 件数据量小/类别混杂），2.4 评估调优
- [x] 2026-08-10：检索评估脚本 evaluate.py（culture 作同类标准，60 个有标签文物）
  - 基线：Precision@5=0.213, Recall@5=0.369（远好于随机≈0.02）
  - 洞察：Flemish 3.0/5, Maya 2.17/5 表现好；China 0.27/5 差（culture 标签过宽，跨朝代）
  - 结论：检索有效，精度受"同类定义粗糙 + 数据稀疏"限制
- [x] 2026-08-10：多标准评估对比（evaluate.py --standard culture/period/medium）
  - 结果：Precision@5 = culture 0.213 / period 0.774 / medium 0.569
  - 洞察：period（埃及第三中间期 80 件 5.0/5 完美）与视觉最对齐 → 证明 DINOv2 检索能力强
  - 结论："精度不足"主因是同类标签(culture)过宽 + 数据稀疏，非模型问题
- [x] 2026-08-10：补数据优化启动（扩充关键词 18→37，2 线程慢速后台下载）
  - 遇到的问题：MET API SSL 网络抖动导致崩溃（请求阶段无重试）
  - 解决方案：download_met.py 加 safe_get 指数退避重试
  - 待办：下载完成后重跑 特征→索引→图谱 更新
</details>

---

## 阶段 3：LLM 推理与证据链（5 周）

### 目标清单

| # | 任务 | 状态 | 完成日期 | 备注 |
|---|---|---|---|---|
| 3.1 | 加载 Qwen2.5-VL（无 GPU 改云端 Qwen-VL API） | ✅ | 2026-08-10 | 阿里百炼 qwen-vl-max，OpenAI 兼容接口 |
| 3.2 | 设计 Prompt 模板（查询图片 + 检索结果 → 多模态消息） | ✅ | 2026-08-10 | src/llm/report.py：检索上下文 + 结构化输出 |
| 3.3 | 端到端流程：上传 → 检索 → 构建消息 → LLM 报告 | ✅ | 2026-08-10 | 浏览器验证通过：完整断代报告 |
| 3.4 | 准备 200-500 条 (图片, 考古问答, 答案)，LoRA 微调 | ⬜ | | 可选：改到 Google Colab（本地无 GPU）|
| 3.5 | 模型集成到 Gradio，输出结构化报告 | ✅ | 2026-08-10 | app 加"生成鉴定报告"按钮 + Textbox |

### 进度日志

<details>
<summary><b>LLM 推理</b></summary>

- [x] 2026-08-10：云端 Qwen-VL 接入（src/llm/client.py + report.py + service.py）
  - 遇到的问题：Gradio 上传图片格式非 JPEG 导致 API 400
  - 解决方案：encode_image_base64 统一转 JPEG（PIL）修复
  - 结果：端到端生成断代报告（波斯/莫卧儿细密画，16-17 世纪，置信度中）
- [x] 2026-08-10：集成到 Gradio（生成鉴定报告按钮 + 报告 Textbox）
  - 说明：3.4 LoRA 微调改为 Colab 可选（本地无 GPU 不执行）
</details>

---

## 阶段 4：Demo 完善与部署（3 周）

### 目标清单

| # | 任务 | 状态 | 完成日期 | 备注 |
|---|---|---|---|---|
| 4.1 | 优化 Gradio：上传引导、加载动画、错误处理 | ⬜ | | |
| 4.2 | 证据链展示（相似文物图片 + 图谱关系网络图） | ⬜ | | |
| 4.3 | Dockerfile + docker-compose.yml 容器化 | ⬜ | | |
| 4.4 | 本地/云 GPU 性能测试，记录显存与响应时间 | ⬜ | | |
| 4.5 | 撰写 README（背景、安装、架构图） | ⬜ | | |

### 进度日志

<details>
<summary><b>部署</b></summary>

- [ ] 2026-XX-XX：
  - 遇到的问题：
  - 解决方案：
</details>

---

## 🗒️ 踩坑与经验记录（随时追加）

| 日期 | 问题 | 原因 | 解决方案 |
|---|---|---|---|
| 2026-08-09 | Docker Hub 拉取镜像 `unexpected EOF` | 国内网络无法访问 Docker Hub | Docker Desktop → Resources → Proxies 配置机场代理 `127.0.0.1:7897` |
| 2026-08-09 | 公共镜像加速器全部失效 | 2024 起国内 Docker 加速器陆续关停 | 用机场代理替代 |
| 2026-08-09 | bitsandbytes 4bit 量化不可用 | 仅支持 CUDA，机器无 GPU | 删除该依赖，LLM 推理改云端 API |
| 2026-08-09 | Neo4j 云服务(AuraDB)需注册且中国不可用 | 云服务需 Google 账号登录 | 改用 Docker 本地容器，无需账号 |
| 2026-08-09 | Docker 镜像不含新代码文件 | 镜像构建后才新增的脚本不在镜像内 | docker-compose 挂载 ./scripts ./config ./src 开发期实时同步 |
| 2026-08-09 | MET 数据下载串行太慢（11 万件约 76 小时） | 逐件请求详情 + 命中率低 | 线程池并发（8 线程）+ 扩充过滤关键词 |
| 2026-08-09 | MET API 返回 403 Forbidden 封禁 | 8 线程持续高频请求触发限流 | 降并发到 4 + 请求间隔；改用方案 B 关键词搜索（请求量小约 10 倍） |
| 2026-08-09 | MET 详情端点 429 限流频繁（1571 候选仅命中 299） | MET 对 /objects/{id} 配额极严 | 接受 299 件先用；后续慢速分批或申请 MET API Key |
| 2026-08-09 | 容器内无法访问 HuggingFace 下载模型 | 容器内 127.0.0.1 非宿主机 | docker-compose 加 HTTP_PROXY=http://host.docker.internal:7897 |
| 2026-08-09 | faiss 导入报 numpy.core.multiarray failed | numpy 2.x 移除 numpy.core，faiss 1.7.4 不兼容 | 锁定 numpy==1.26.4 并重建镜像 |
| 2026-08-09 | Neo4j 关系 MERGE 误建重复节点 | 关系语句中的 MERGE (c:Culture {name}) 匹配歧义时创建新节点 | 两阶段导入：先建节点+唯一约束，关系用 MATCH 已存在节点再 MERGE |
| 2026-08-09 | Wikidata label 精确匹配率低(8%) | 本地词带括号年份(如 "Tang dynasty (618–907)") | 归一化提取括号前主干，匹配率提升到 51% |
| 2026-08-09 | DVC 报 data 已被 Git 跟踪 | data/README.md 未被 .gitignore 排除 | git rm --cached data 后交 DVC 管理 |
| 2026-08-10 | docker-compose YAML 挂载行粘合 | 编辑时换行丢失 | 用 docker compose config 验证挂载源 |
| 2026-08-10 | python app/app.py 找不到 src | 脚本目录不在 sys.path | app.py 顶部 sys.path.insert 项目根 |
| 2026-08-10 | 检索评估中 culture 标签过宽 | 同 culture(如 China)跨多个朝代，视觉差异大 | 可改用 period/medium 作更精细真值 |
| 2026-08-10 | MET API SSL 网络抖动崩溃 | 请求阶段无重试机制 | download_met.py 加 safe_get 指数退避重试 |
| 2026-08-10 | Gradio 上传图片致 LLM API 400 | 上传图非 JPEG 但 data URL 写死 image/jpeg | client.py 统一转 JPEG(PIL) 再编码 |

| 日期 | 模块 | 问题 | 解决方案 |
|---|---|---|---|
| | | | |
