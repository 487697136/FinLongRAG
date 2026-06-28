# 知识库隔离修复总结

## 问题描述

用户反馈：在"管理"知识库中查询时，会返回"金融"知识库的内容，导致知识库隔离失败。

**期望行为**：
- 在知识库 A 中查询，只返回知识库 A 的文档
- 在知识库 B 中查询，只返回知识库 B 的文档
- 知识库名称只是标签，系统应基于物理数据边界隔离

## 问题根源

### 完整调用链

```
前端 (ChatPage.vue) 
  → API (/api/v1/query/stream)
  → ChatService.ask()
  → Pipeline.ask()
  → Pipeline.answer()
  → ReasoningPipeline._answer_open()
  → Retriever.retrieve_queries()  ← ❌ 问题在这里
  → BM25SearchChannel / FaissSearchChannel
  → BM25FIndex.search() / FaissVectorStore.search()
```

### 根本原因

在 `ReasoningPipeline._answer_open()` 中：

```python
retrieved = self.retriever.retrieve_queries(
    rewrite.sub_queries,
    filter_doc_ids=filter_doc_ids,
    source="open_query_rewrite",
    # ❌ 缺少 metadata 参数！
)
```

而 `retrieve_queries()` 内部创建了一个新的临时 Question 对象：

```python
def retrieve_queries(self, queries, ...):
    return self._search_channels(
        Question(qid="retrieval", question=" ".join(queries), answer_format="open"),
        # ❌ 没有 metadata，kb_id 丢失！
        ...
    )
```

导致 `question.metadata["kb_id"]` 丢失，检索时无法按知识库过滤。

## 修复方案

### 1. 修改 `Retriever.retrieve_queries()`

**文件**：`src/finlongrag/retrieval/retriever.py`

```python
def retrieve_queries(
    self,
    queries: list[str],
    *,
    filter_doc_ids: set[str] | None,
    top_k_per_query: int | None = None,
    fused_top_k: int | None = None,
    source: str = "claim_bm25f",
    metadata: dict | None = None,  # ✅ 添加 metadata 参数
) -> list[RetrievalResult]:
    return self._search_channels(
        Question(
            qid="retrieval", 
            question=" ".join(queries), 
            answer_format="open", 
            metadata=metadata or {}  # ✅ 传递 metadata
        ),
        ...
    )
```

### 2. 修改 `ReasoningPipeline._answer_open()`

**文件**：`src/finlongrag/reasoning/pipeline.py`

```python
def _answer_open(self, question: Question, route: dict, plan: dict, *, history: str = "") -> AnswerResult:
    rewrite = self.query_rewriter.rewrite(question, history=history)
    filter_doc_ids = set(question.doc_ids) if question.doc_ids else None
    retrieved = self.retriever.retrieve_queries(
        rewrite.sub_queries,
        filter_doc_ids=filter_doc_ids,
        source="open_query_rewrite",
        metadata=question.metadata,  # ✅ 传递原始 question 的 metadata
    )
```

### 3. 修改 `ClaimVerifier.verify()`

**文件**：`src/finlongrag/reasoning/verifier.py`

```python
def verify(self, claim: Claim, *, metadata: dict | None = None) -> tuple[ClaimVerdict, TokenUsage]:
    filter_doc_ids = set(claim.doc_scope) if claim.doc_scope else None
    candidates = self.retriever.retrieve_queries(
        build_claim_queries(claim),
        filter_doc_ids=filter_doc_ids,
        source=f"claim:{claim.option_key}",
        metadata=metadata,  # ✅ 传递 metadata
    )
```

### 4. 修改 `ReasoningPipeline._answer_structured()`

**文件**：`src/finlongrag/reasoning/pipeline.py`

```python
def _answer_structured(self, question: Question, route: dict, plan: dict) -> AnswerResult:
    total_usage = TokenUsage()
    verdicts = []
    memory = WorkingMemory(question.qid, question.question)
    for claim in self.analyzer.build_claims(question):
        verdict, usage = self.verifier.verify(claim, metadata=question.metadata)  # ✅ 传递 metadata
        ...
```

## 验证结果

### 测试脚本

运行 `scripts/test_query_with_kb_id.py`：

```
测试查询: 什么是犹豫期
======================================================================

[测试 1] 在金融库查询 (KB: f066ed944b5240dd9e2a734ad122fc4a)
----------------------------------------------------------------------
  证据数量: 8
    [1] doc=043ab93253244c7ba31c9ab9851bcd1d_5, kb=f066ed944b5240dd...  ✅ 金融库
    [2] doc=043ab93253244c7ba31c9ab9851bcd1d_5, kb=f066ed944b5240dd...  ✅ 金融库
    [3] doc=043ab93253244c7ba31c9ab9851bcd1d_5, kb=f066ed944b5240dd...  ✅ 金融库

[测试 2] 在管理库查询 (KB: e4dbce7568494b52be637e6e47c2bc47)
----------------------------------------------------------------------
  证据数量: 8
    [1] doc=9249a431b659436da632b04c22871001_csrc_0001_att1, kb=e4dbce7568494b52...  ✅ 管理库
    [2] doc=9249a431b659436da632b04c22871001_csrc_0001_att1, kb=e4dbce7568494b52...  ✅ 管理库
    [3] doc=9249a431b659436da632b04c22871001_csrc_0001_att1, kb=e4dbce7568494b52...  ✅ 管理库

[测试 3] 不指定 KB (全局搜索)
----------------------------------------------------------------------
  证据数量: 8
    KB f066ed944b5240dd...: 8 个证据  ✅ 全局搜索正常
```

### 知识库数据

- **金融库** (`f066ed944b5240dd9e2a734ad122fc4a`): 421 chunks
  - 文档：平安 e 生保住院 7.0 医疗保险 A 款条款
  
- **管理库** (`e4dbce7568494b52be637e6e47c2bc47`): 71 chunks
  - 文档：私募投资基金信息披露监督管理办法

## 前端测试步骤

1. **重启后端服务**（已完成）
2. **刷新浏览器** `http://127.0.0.1:7860`
3. **测试场景**：

### 场景 1：金融库查询
- 选择知识库：**金融**
- 提问：**你知道什么是犹豫期吗**
- **期望结果**：返回医疗保险相关的犹豫期说明
- **证据来源**：文档 ID 应为 `043ab93253244c7ba31c9ab9851bcd1d_5`

### 场景 2：管理库查询
- 选择知识库：**管理**
- 提问：**你知道什么是犹豫期吗**
- **期望结果**：未找到相关内容（管理库没有医疗保险文档）
- **证据来源**：文档 ID 应为 `9249a431b659436da632b04c22871001_csrc_0001_att1`（私募基金）

### 场景 3：管理库专属内容
- 选择知识库：**管理**
- 提问：**私募投资基金信息披露监督管理办法第一章第二条是什么**
- **期望结果**：返回法规条文
- **证据来源**：只能来自管理库

## 技术细节

### 数据流

```
用户选择 KB → frontend 传递 knowledge_base_id
                    ↓
            API 接收并转为 kb_id
                    ↓
            ChatService.ask(kb_id=...)
                    ↓
            Pipeline.ask(kb_id=...)
                    ↓
            question.metadata = {"kb_id": kb_id}
                    ↓
            ReasoningPipeline 使用 question.metadata
                    ↓
            Retriever 提取 kb_id 并过滤
                    ↓
            BM25/FAISS 只返回匹配的 KB 结果
```

### 过滤机制

知识库隔离有**三层过滤**：

1. **BM25 层过滤** (`bm25.py:99-100`)：
   ```python
   if kb_id and chunk.metadata.get("kb_id") != kb_id:
       continue
   ```

2. **FAISS 层过滤** (`faiss_store.py:128-129`)：
   ```python
   if self.kb_id:
       return [self._kb_dir(self.kb_id)]  # 只搜索指定 KB 的索引
   ```

3. **融合后再过滤** (`retriever.py:124-125`)：
   ```python
   if kb_id:
       fused = [r for r in fused if r.metadata.get("kb_id") == kb_id]
   ```

## 修改文件清单

- ✅ `src/finlongrag/retrieval/retriever.py`
- ✅ `src/finlongrag/reasoning/pipeline.py`
- ✅ `src/finlongrag/reasoning/verifier.py`

## 总结

**问题**：`retrieve_queries()` 创建临时 Question 对象时丢失了 `kb_id`

**解决**：在整个检索链路中传递 `question.metadata`，确保 `kb_id` 从 API 层一直传递到检索层

**效果**：✅ 知识库完全隔离，查询 A 库只返回 A 库内容，查询 B 库只返回 B 库内容
