# FinLongRAG

FinLongRAG 是一个面向金融长文档问答场景的 RAG 系统，支持文档入库、混合检索、证据重排、多轮问答和检索评测。项目由 FastAPI 后端和 Vue 3 前端组成，使用 PostgreSQL 管理业务数据，使用 FAISS 保存向量索引，并通过 DashScope 调用 Qwen、Embedding 和 Rerank 模型。

## 主要功能

- 知识库管理：创建知识库、上传文档、查看文档处理状态。
- 文档处理：解析 PDF、文本、Markdown、Office、CSV、JSON/JSONL 等文件，并进行结构化分块。
- 混合检索：结合 BM25F 关键词检索和 FAISS 向量检索，通过 RRF 融合候选证据。
- 证据增强问答：支持 DashScope `qwen3-rerank` 重排、证据筛选、引用校验和 Qwen 答案生成。
- 多轮会话：保留会话记录，支持基于上下文的连续问答。
- 评测中心：管理测试集，运行检索评测，查看评测报告。
- 本地运维脚本：提供环境配置、数据库初始化、运行检查、入库和索引构建脚本。

## 技术栈

| 模块 | 技术 |
| --- | --- |
| 后端服务 | FastAPI, Uvicorn, Pydantic 2 |
| 前端应用 | Vue 3, Vite, Naive UI, Pinia |
| 数据库 | PostgreSQL |
| ORM / 迁移 | SQLAlchemy, Alembic |
| 文档解析 | opendataloader-pdf, pypdf |
| 关键词检索 | BM25F |
| 向量检索 | FAISS |
| 模型服务 | DashScope / Qwen |
| 测试与检查 | pytest, ruff |

## 目录结构

```text
FinLongRAG/
  alembic/                 数据库迁移脚本
  config/                  应用默认配置
  data/raw_dataset/        演示数据
  docs/                    架构、运行和交接文档
  frontend/                Vue 前端应用
  scripts/                 环境、启动、入库、索引和检查脚本
  src/finlongrag/          后端服务与 RAG 核心代码
  tests/                   自动化测试
```

## 环境要求

推荐使用以下环境：

- Windows 10/11
- Python 3.12
- Node.js 20+ 或 22+
- PostgreSQL 18
- Java 11+，用于 PDF 解析
- DashScope API Key

项目依赖见 [requirements.txt](requirements.txt) 和 [frontend/package.json](frontend/package.json)。开发和测试依赖见 [requirements-dev.txt](requirements-dev.txt)。

## 配置

复制环境变量模板：

```powershell
copy .env.example .env
```

至少需要配置以下内容：

```text
DASHSCOPE_API_KEY=<your DashScope API Key>
FINLONGRAG_DATABASE_URL=postgresql://finlongrag:finlongrag@localhost:5432/finlongrag
FINLONGRAG_QWEN_MODEL=qwen-plus
FINLONGRAG_VECTOR_EMBEDDING_MODEL=text-embedding-v4
FINLONGRAG_VECTOR_DIMENSION=1024
FINLONGRAG_RERANK_MODEL=qwen3-rerank
FINLONGRAG_SECRET_KEY=<replace with a long random secret>
```

完整配置项可参考 [.env.example](.env.example) 和 [config/finlongrag.yaml](config/finlongrag.yaml)。

## 安装

### Python 环境

推荐使用项目脚本创建 Conda 环境：

```powershell
.\scripts\setup_env.ps1
```

如果 Conda 不在默认路径，可以显式指定：

```powershell
.\scripts\setup_env.ps1 -CondaExe "E:\Anaconda3\Scripts\conda.exe" -EnvRoot "E:\Anaconda3"
```

也可以手动创建虚拟环境：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
```

### 数据库

初始化应用数据库和用户：

```powershell
.\scripts\init_postgres.ps1
```

执行迁移：

```powershell
E:\Anaconda3\envs\finlongrag-py312\python.exe -m alembic upgrade head
```

如果使用 `.venv`：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

### 前端

```powershell
cd frontend
npm install
npm run build
cd ..
```

## 启动

直接启动：

```powershell
.\start.bat
```

或使用 PowerShell 脚本指定服务地址：

```powershell
.\scripts\start.ps1 -HostName 127.0.0.1 -Port 7860
```

启动后访问：

```text
http://127.0.0.1:7860
```

默认本地账号：

```text
admin / finlongrag
```

正式部署前请修改 `.env` 中的默认账号密码和 `FINLONGRAG_SECRET_KEY`。

## 运行检查

检查本地配置、数据库、Java、FAISS 和 PDF 解析依赖：

```powershell
E:\Anaconda3\envs\finlongrag-py312\python.exe scripts\check_runtime.py
```

同时检查 DashScope Embedding 和 Rerank 调用：

```powershell
E:\Anaconda3\envs\finlongrag-py312\python.exe scripts\check_runtime.py --models
```

常用质量检查：

```powershell
E:\Anaconda3\envs\finlongrag-py312\python.exe -m compileall -q src scripts tests
E:\Anaconda3\envs\finlongrag-py312\python.exe -m ruff check src scripts tests
E:\Anaconda3\envs\finlongrag-py312\python.exe -m pytest
E:\Anaconda3\envs\finlongrag-py312\python.exe -m pip check

cd frontend
npm run build
```

## 处理流程

```text
上传文件
  -> 本地文件存储
  -> 文档解析
  -> 结构化分块
  -> PostgreSQL 入库
  -> BM25F 索引
  -> DashScope Embedding
  -> FAISS 向量索引
  -> BM25F + FAISS 召回
  -> RRF 融合
  -> qwen3-rerank 重排
  -> Qwen 生成答案
```

默认运行数据位置：

```text
data/object_storage/      上传原文
data/processed/           解析和处理中间结果
data/index/               检索索引
output/                   运行输出
```

## 提交前检查

提交到 GitHub 前建议运行：

```powershell
git status --short
git ls-files -o --exclude-standard
```

建议提交源码、配置模板、迁移脚本、文档、测试、前端源码和锁文件。`.env`、虚拟环境、依赖目录、构建产物、索引文件、上传文件、输出日志和缓存目录应保留在本地。
