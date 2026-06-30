# FinLongRAG 架构说明

当前架构为 PostgreSQL 18 + 本地 FAISS 向量索引 + DashScope 模型调用。PostgreSQL 保存业务数据，FAISS 保存 chunk 向量索引文件。

项目不使用 SQLite、Docker、数据库向量扩展、本地伪向量或启发式重排。

## 主链路

```text
Frontend
  -> FastAPI /api/v1
  -> KnowledgeService / ChatService
  -> PostgreSQL 18
  -> BM25F Index + FAISS
  -> RRF Fusion
  -> qwen3-rerank
  -> Qwen Chat
  -> SSE / REST Response
```

## 文档入库

```text
Upload
  -> FileStorage
  -> OpenDataLoader PDF (opendataloader-pdf, requires Java 11+)
  -> Structure-aware Chunker
  -> SQLAlchemyKnowledgeRepository
  -> PostgreSQL knowledge_chunks
  -> BM25F / DocumentIndex
  -> DashScopeEmbeddingProvider
  -> FAISS index.faiss + metadata.jsonl
```

Agent 问答主链路（开放题 RAG）：

```text
Router (LLM) -> Planner
  -> AgentRuntime (intent / budget / cache)
  -> StepExecutor:
       rewrite_query -> hybrid_retrieve -> conditional rerank -> select_evidence
       -> assess_evidence -> generate_answer (+ numeric tools) -> validate_citations
```

入库编排：

```text
Upload -> IngestionPipeline(parse -> chunk) -> PostgreSQL -> build_indexes -> merge_global_indexes
```

说明：对话路由与结构化选择题仍走专用路径，未统一经过 StepExecutor；知识图谱能力暂未实现（API 返回 501，前端入口保留搁置）。

## 搁置功能（暂不开发）

- 知识图谱：`POST .../rebuild-graph`、`POST .../cleanup` 返回 501；`GET .../graph` 返回空数据
- 前端图谱页面保留，对接上述 stub API

## 检索模块

- `index/bm25.py`：关键词检索，处理金融术语、日期、金额、法规编号和条款号。
- `index/faiss_store.py`：本地 FAISS 向量索引构建、持久化和检索。
- `index/providers.py`：DashScope Embedding Provider。
- `retrieval/channels.py`：BM25F 和 FAISS 检索通道。
- `retrieval/retriever.py`：多 query、多通道 RRF 融合。
- `retrieval/rerank.py`：DashScope qwen3-rerank 重排。

## 存储

- PostgreSQL 18：用户、知识库、文档、Chunk、会话、任务、评测和索引版本。
- 本地文件系统：上传原文件、BM25F 索引、DocumentIndex、FAISS 索引和运行输出。
- `data/index/faiss/<kb_id>/index.faiss`：FAISS 向量索引。
- `data/index/faiss/<kb_id>/metadata.jsonl`：FAISS 行号对应的 chunk metadata。
