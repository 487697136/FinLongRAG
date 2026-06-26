# FinLongRAG 配置与交接文档

本文面向团队成员本地配置和项目交接。当前项目采用 PostgreSQL 18 + 本地 FAISS 向量索引，不支持 SQLite，不使用 Docker，也不需要数据库向量扩展。

## 1. 必要环境

- Windows 10 / 11
- Anaconda，建议安装在 `E:\Anaconda3`
- Python 3.12
- Node.js 20+ 或 22+
- PostgreSQL 18
- DashScope API Key

## 2. Python 环境

首次配置：

```powershell
cd E:\课程项目\short_term\FinLongRAG
.\scripts\setup_env.ps1
```

已有环境时更新依赖：

```powershell
E:\Anaconda3\envs\finlongrag-py312\python.exe -m pip install -r requirements.txt
E:\Anaconda3\envs\finlongrag-py312\python.exe -m pip install -e . --no-deps
```

## 3. PostgreSQL 初始化

如果本机还没有 `finlongrag` 数据库和 `finlongrag` 应用用户，执行：

```powershell
.\scripts\init_postgres.ps1
```

执行迁移：

```powershell
E:\Anaconda3\envs\finlongrag-py312\python.exe -m alembic upgrade head
```

## 4. 环境变量

复制模板：

```powershell
copy .env.example .env
```

必须确认：

```text
DASHSCOPE_API_KEY=<你的 DashScope API Key>
FINLONGRAG_DATABASE_URL=postgresql://finlongrag:finlongrag@localhost:5432/finlongrag
FINLONGRAG_VECTOR_STORE=faiss
FINLONGRAG_VECTOR_EMBEDDING_PROVIDER=dashscope
FINLONGRAG_VECTOR_EMBEDDING_MODEL=text-embedding-v4
FINLONGRAG_VECTOR_DIMENSION=1024
FINLONGRAG_RERANK_PROVIDER=dashscope
FINLONGRAG_RERANK_MODEL=qwen3-rerank
FINLONGRAG_SECRET_KEY=<随机长字符串>
```

`.env` 不提交 GitHub。不同设备应从 `.env.example` 复制并填写本机配置。

## 5. 前端

```powershell
cd E:\课程项目\short_term\FinLongRAG\frontend
npm install
npm run build
```

## 6. 启动

```powershell
cd E:\课程项目\short_term\FinLongRAG
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

## 7. 运行时检查

```powershell
E:\Anaconda3\envs\finlongrag-py312\python.exe scripts\check_runtime.py
E:\Anaconda3\envs\finlongrag-py312\python.exe scripts\check_runtime.py --models
```

## 8. 当前真实链路

```text
文件存储 -> 解析 -> Chunk 切分 -> PostgreSQL 入库 -> BM25F 索引
-> DashScope Embedding -> FAISS index.faiss + metadata.jsonl
-> BM25F + FAISS 召回 -> RRF -> qwen3-rerank -> Qwen 生成
```

## 9. 常见问题

- 上传文档后没有向量索引：检查 `data/index/faiss/<kb_id>/index.faiss` 和 `metadata.jsonl` 是否生成。
- `faiss` 导入失败：执行 `E:\Anaconda3\envs\finlongrag-py312\python.exe -m pip install faiss-cpu==1.14.3`。
- DashScope embedding 失败：确认 `.env` 中 `DASHSCOPE_API_KEY` 有效。
- 数据库连接失败：确认 PostgreSQL 服务、数据库、用户、密码和 `.env` 一致。
