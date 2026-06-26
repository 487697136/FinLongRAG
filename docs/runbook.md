# FinLongRAG 运行手册

## 1. PostgreSQL 检查

确认 PostgreSQL 18 服务运行：

```powershell
Get-Service postgresql-x64-18
```

如果目标数据库和应用用户尚未创建：

```powershell
.\scripts\init_postgres.ps1
```

然后运行迁移：

```powershell
E:\Anaconda3\envs\finlongrag-py312\python.exe -m alembic upgrade head
```

## 2. 启动服务

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

## 3. 运行时检查

基础检查：

```powershell
E:\Anaconda3\envs\finlongrag-py312\python.exe scripts\check_runtime.py
```

同时检查 DashScope embedding 和 rerank：

```powershell
E:\Anaconda3\envs\finlongrag-py312\python.exe scripts\check_runtime.py --models
```

接口健康检查：

```text
GET /api/health
```

重点查看：

- `vector_store` 应为 `faiss`
- `embedding_provider` 应为 `dashscope`
- `rerank_provider` 应为 `dashscope`

## 4. 文档处理流程

```text
上传文件 -> 本地文件存储 -> 解析 -> Chunk 切分 -> PostgreSQL 入库
-> BM25F 索引 -> DashScope Embedding -> FAISS 写入 -> 问答检索
```

FAISS 文件位置：

```text
data/index/faiss/<kb_id>/index.faiss
data/index/faiss/<kb_id>/metadata.jsonl
data/index/faiss/<kb_id>/manifest.json
```

## 5. 常见问题

### PostgreSQL 连接失败

当前项目要求 `FINLONGRAG_DATABASE_URL` 在本机 `.env` 中明确配置。需要执行：

```powershell
.\scripts\init_postgres.ps1
```

或把 `.env` 中 `FINLONGRAG_DATABASE_URL` 改为实际可用的 PostgreSQL 用户、密码和数据库。

### FAISS 导入失败

执行：

```powershell
E:\Anaconda3\envs\finlongrag-py312\python.exe -m pip install faiss-cpu==1.14.3
```

### 向量索引没有生成

检查文档任务是否成功，并确认：

```text
data/index/faiss/<kb_id>/index.faiss
data/index/faiss/<kb_id>/metadata.jsonl
```

如果没有生成，通常是 DashScope embedding 调用失败或文档解析没有产生 chunk。

### DashScope 调用失败

确认 `.env` 中：

```text
DASHSCOPE_API_KEY=<有效密钥>
FINLONGRAG_VECTOR_EMBEDDING_MODEL=text-embedding-v4
FINLONGRAG_RERANK_MODEL=qwen3-rerank
```

## 6. 质量检查

```powershell
E:\Anaconda3\envs\finlongrag-py312\python.exe -m pip check
E:\Anaconda3\envs\finlongrag-py312\python.exe -m compileall -q src scripts tests
E:\Anaconda3\envs\finlongrag-py312\python.exe -m ruff check src scripts tests
E:\Anaconda3\envs\finlongrag-py312\python.exe -m pytest

cd frontend
npm run build
```
