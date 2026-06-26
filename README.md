# FinLongRAG

FinLongRAG 是面向金融长文本的 Agentic RAG 问答与服务系统。当前项目采用 **PostgreSQL 18 + 本地 FAISS 向量索引 + DashScope/Qwen 模型调用**，目标是支持文档上传、解析、索引、持续对话、检索增强问答和检索评测。

项目不使用 SQLite，不使用 Docker，不依赖数据库向量扩展，不保留本地伪向量或启发式重排。

## 当前能力

| 模块 | 选型 |
| --- | --- |
| 后端 | FastAPI + Pydantic 2 + Uvicorn |
| 前端 | Vue 3 + JavaScript + Vite + Naive UI |
| 主数据库 | PostgreSQL 18 |
| 向量检索 | FAISS 本地索引 |
| Embedding | DashScope `text-embedding-v4` |
| 重排 | DashScope `qwen3-rerank` |
| 关键词检索 | BM25F |
| 检索融合 | RRF |
| 大模型回答 | Qwen / DashScope OpenAI 兼容接口 |
| 文件存储 | 本地文件系统 |
| 后台任务 | ThreadPoolExecutor |

## 目录说明

```text
FinLongRAG/
  alembic/                 PostgreSQL 业务表迁移脚本。
  config/                  应用默认配置。
  data/                    本地运行数据目录，生成数据不提交 Git。
  docs/                    架构、运行、依赖和交接文档。
  frontend/                Vue 前端项目。
  output/                  本地输出目录，不提交 Git。
  scripts/                 环境、启动、数据库初始化和检查脚本。
  src/finlongrag/          后端与核心 Agent 代码。
  tests/                   自动化测试。
```

`data/index/faiss/` 保存 FAISS 向量索引和 chunk metadata，属于本地生成文件，不提交 Git。

## 环境要求

- Windows 10 / 11
- Anaconda，建议安装在 `E:\Anaconda3`
- Python 3.12
- Node.js 20+ 或 22+
- PostgreSQL 18
- DashScope API Key

## 初始化

复制环境变量模板：

```powershell
copy .env.example .env
```

关键配置：

```text
DASHSCOPE_API_KEY=<你的 DashScope API Key>
FINLONGRAG_DATABASE_URL=postgresql://finlongrag:finlongrag@localhost:5432/finlongrag
FINLONGRAG_VECTOR_STORE=faiss
FINLONGRAG_VECTOR_EMBEDDING_PROVIDER=dashscope
FINLONGRAG_VECTOR_EMBEDDING_MODEL=text-embedding-v4
FINLONGRAG_VECTOR_DIMENSION=1024
FINLONGRAG_RERANK_PROVIDER=dashscope
FINLONGRAG_RERANK_MODEL=qwen3-rerank
```

初始化 PostgreSQL 用户和数据库：

```powershell
.\scripts\init_postgres.ps1
```

执行迁移：

```powershell
E:\Anaconda3\envs\finlongrag-py312\python.exe -m alembic upgrade head
```

## 启动

```powershell
.\start.bat
```

访问：

```text
http://127.0.0.1:7860
```

默认账号：

```text
admin / finlongrag
```

## 文档处理链路

```text
上传文件
  -> 本地文件存储
  -> 文档解析
  -> 结构感知 Chunk
  -> PostgreSQL 入库
  -> BM25F / DocumentIndex
  -> DashScope text-embedding-v4
  -> FAISS index.faiss + metadata.jsonl
  -> BM25F + FAISS 召回
  -> RRF 融合
  -> qwen3-rerank
  -> Qwen 生成答案
```

## 运行检查

```powershell
E:\Anaconda3\envs\finlongrag-py312\python.exe scripts\check_runtime.py
E:\Anaconda3\envs\finlongrag-py312\python.exe scripts\check_runtime.py --models
```

## 验证命令

```powershell
E:\Anaconda3\envs\finlongrag-py312\python.exe -m compileall -q src scripts tests
E:\Anaconda3\envs\finlongrag-py312\python.exe -m ruff check src scripts tests
E:\Anaconda3\envs\finlongrag-py312\python.exe -m pytest
E:\Anaconda3\envs\finlongrag-py312\python.exe -m pip check

cd frontend
npm run build
```

## GitHub 提交注意

提交源码、配置模板、迁移、脚本、文档和前端源码；不要提交 `.env`、`frontend/node_modules/`、`frontend/dist/`、`data/index/`、`data/processed/`、`data/object_storage/`、`output/`、缓存目录和日志。
