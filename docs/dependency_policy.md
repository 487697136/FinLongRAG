# 依赖说明与维护策略

FinLongRAG 当前只面向 PostgreSQL 18 + 本地 FAISS 向量索引 + DashScope 模型调用。

## 关键运行依赖

| 依赖 | 用途 |
| --- | --- |
| fastapi / starlette / uvicorn | 后端 API 服务 |
| pydantic | 参数校验和 Schema |
| sqlalchemy / alembic | ORM 和数据库迁移 |
| psycopg[binary] | PostgreSQL 18 驱动 |
| asyncpg | 异步 PostgreSQL 连接能力 |
| faiss-cpu | 本地向量索引和相似度检索 |
| httpx / requests | DashScope / Qwen API 调用 |
| python-dotenv | 加载 `.env` |
| python-multipart | 文件上传 |
| PyJWT | JWT 认证 |
| PyMuPDF | PDF 解析 |
| openpyxl | XLSX 读取 |
| jieba | 中文分词和 BM25F |
| numpy | 向量和数值处理 |
| PyYAML | YAML 配置 |

## 不引入的依赖

| 依赖或能力 | 原因 |
| --- | --- |
| SQLite 驱动 | 项目已经改为 PostgreSQL-only |
| 数据库向量扩展 | Windows 服务端扩展配置成本较高，已改为 FAISS |
| Docker SDK / compose 依赖 | 当前使用本机 PostgreSQL 18 |
| Qdrant / Milvus | 当前阶段使用本地 FAISS，减少外部服务 |
| Redis / Celery / RQ | 当前使用本地线程任务执行器 |

## 验证命令

```powershell
E:\Anaconda3\envs\finlongrag-py312\python.exe -m pip check
E:\Anaconda3\envs\finlongrag-py312\python.exe -m compileall -q src scripts tests
E:\Anaconda3\envs\finlongrag-py312\python.exe -m ruff check src scripts tests
E:\Anaconda3\envs\finlongrag-py312\python.exe -m pytest
```
