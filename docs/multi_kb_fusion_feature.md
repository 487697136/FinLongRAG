# 多知识库融合功能实现总结

## 功能描述

实现了一个智能的知识库选择机制，通过一个"融合"开关控制单库隔离和多库融合两种模式：

### 模式 1：单库隔离（开关关闭）
- **行为**：只能选择一个知识库
- **检索范围**：严格限定在选中的知识库内
- **用例**：需要精确查询特定领域内容，避免跨库干扰

### 模式 2：多库融合（开关打开）
- **行为**：可以多选知识库（1个或多个）
- **检索范围**：融合所有选中知识库的内容
- **用例**：需要跨领域综合查询，获取更全面的答案

---

## 实现细节

### 前端修改

#### 1. UI 组件调整

**文件**：`frontend/src/views/chat/ChatPage.vue`

**主输入区**（home 场景）：
```vue
<!-- 单库模式：普通下拉框 -->
<n-select
  v-if="!useAutoMode"
  v-model:value="selectedKnowledgeBaseId"
  :options="knowledgeBaseOptions"
  placeholder="选择知识库"
  size="small"
/>

<!-- 多库模式：多选下拉框 -->
<n-select
  v-else
  v-model:value="selectedKnowledgeBaseIds"
  :options="knowledgeBaseOptions"
  placeholder="选择知识库（可多选）"
  size="small"
  multiple
  max-tag-count="responsive"
/>

<!-- 融合开关 -->
<div class="mode-auto-switch" :class="{ 'mode-auto-switch--on': useAutoMode }">
  <div class="mode-auto-switch__text">
    <div class="mode-auto-switch__title">融合</div>
    <div class="mode-auto-switch__desc">{{ useAutoMode ? '多库融合' : '单库隔离' }}</div>
  </div>
  <n-switch v-model:value="useAutoMode" size="small" />
</div>
```

**会话输入区**（session 场景）：
```vue
<div class="mode-auto-switch mode-auto-switch--sm">
  <div class="mode-auto-switch__text">
    <div class="mode-auto-switch__title">融合</div>
    <div class="mode-auto-switch__desc">{{ useAutoMode ? '多库' : '单库' }}</div>
  </div>
  <n-switch v-model:value="useAutoMode" size="small" />
</div>
```

#### 2. 状态管理

**新增状态**：
```javascript
const selectedKnowledgeBaseId = ref('')          // 单选 KB ID
const selectedKnowledgeBaseIds = ref([])         // 多选 KB IDs
const useAutoMode = ref(false)                   // 默认关闭，单库模式
```

**状态同步**：
```javascript
// 当开关切换时，自动同步单选和多选状态
watch(useAutoMode, (isMulti) => {
  if (isMulti) {
    // 切换到多选：将单选值转为数组
    if (selectedKnowledgeBaseId.value) {
      selectedKnowledgeBaseIds.value = [selectedKnowledgeBaseId.value]
    }
  } else {
    // 切换到单选：取多选数组的第一个
    if (selectedKnowledgeBaseIds.value.length > 0) {
      selectedKnowledgeBaseId.value = selectedKnowledgeBaseIds.value[0]
    }
  }
})
```

#### 3. 请求参数构建

```javascript
const requestPayload = {
  question: questionText,
  session_id: activeConversation.value?.session?.id || undefined,
  mode: effectiveSendMode.value,
  top_k: 20,
  use_memory: true,
  memory_turn_window: 4,
  llm_provider: selectedLlmProvider.value || undefined,
  llm_model: selectedLlmModel.value || undefined
}

if (useAutoMode.value) {
  // 多库融合模式：传递 kb_ids 数组
  requestPayload.kb_ids = selectedKnowledgeBaseIds.value.length > 0
    ? selectedKnowledgeBaseIds.value
    : undefined
} else {
  // 单库隔离模式：传递单个 kb_id
  requestPayload.knowledge_base_id = selectedKnowledgeBaseId.value
}
```

#### 4. 查询前验证

```javascript
const ensureReadyForQuery = () => {
  if (effectiveSendMode.value === 'llm_only') return true

  // 多库融合模式
  if (useAutoMode.value) {
    if (selectedKnowledgeBaseIds.value.length === 0) {
      message.warning('请先选择至少一个知识库')
      return false
    }
    return true
  }

  // 单库隔离模式
  if (!selectedKnowledgeBaseId.value) {
    message.warning('请先选择知识库')
    return false
  }
  if (!selectedKnowledgeBaseStats.value?.initialized) {
    message.warning('当前知识库尚未初始化，请先上传文档完成处理')
    return false
  }
  return true
}
```

---

### 后端修改

#### 1. API 请求模型

**文件**：`src/finlongrag/api/v1.py`

```python
class QueryRequest(BaseModel):
    question: str = Field(min_length=1)
    knowledge_base_id: str | int | None = None  # 单库模式
    kb_ids: list[str] | None = None             # 多库模式
    session_id: str | int | None = None
    mode: str = "auto"
    top_k: int = 20
    use_memory: bool = True
    memory_turn_window: int = 4
    llm_provider: str | None = None
    llm_model: str | None = None
```

#### 2. API 处理逻辑

```python
@router.post("/query/stream")
def query_stream(payload: QueryRequest, user: User = Depends(current_user)) -> StreamingResponse:
    question = payload.question.strip()

    # 处理单 KB 或多 KB 模式
    kb_id = None
    kb_ids = None
    if payload.kb_ids:
        # 多知识库融合模式
        kb_ids = [str(kid) for kid in payload.kb_ids if kid]
        kb_id = kb_ids[0] if kb_ids else ""  # 用于 conversation metadata
    elif payload.knowledge_base_id:
        # 单知识库隔离模式
        kb_id = str(payload.knowledge_base_id)

    def event_stream():
        # ...
        response = chat.ask(
            question,
            conversation_id=conversation_id,
            kb_id=kb_id or None,
            kb_ids=kb_ids
        )
        # ...
```

#### 3. ChatService 层

**文件**：`src/finlongrag/conversation/service.py`

```python
def ask(
    self,
    message: str,
    *,
    conversation_id: str | None = None,
    domain: str = "",
    doc_ids: list[str] | None = None,
    kb_id: str | None = None,
    kb_ids: list[str] | None = None,  # 新增
) -> ChatResponse:
    # ...
    result = self.pipeline.ask(
        message,
        domain=domain,
        doc_ids=doc_ids or [],
        kb_id=kb_id,
        kb_ids=kb_ids,  # 传递多 KB
        qid=f"chat_{conversation.conversation_id}_{user_message.message_id[:8]}",
        history=history,
    )
```

#### 4. Pipeline 层

**文件**：`src/finlongrag/service/pipeline.py`

```python
def ask(
    self,
    text: str,
    *,
    domain: str = "",
    doc_ids: list[str] | None = None,
    kb_id: str | None = None,
    kb_ids: list[str] | None = None,  # 新增
    qid: str = "adhoc",
    history: str = "",
) -> AnswerResult:
    question = Question(
        qid=qid,
        question=text,
        domain=domain,
        doc_ids=doc_ids or [],
        answer_format="open",
    )
    # 处理多知识库融合或单知识库隔离
    if kb_ids:
        question.metadata = {"kb_ids": kb_ids}
    elif kb_id:
        question.metadata = {"kb_id": kb_id}
    return self.answer(question, history=history)
```

#### 5. Retriever 层

**文件**：`src/finlongrag/retrieval/retriever.py`

```python
def _search_channels(self, question: Question, queries: list[str], ...) -> list[RetrievalResult]:
    # 提取 kb_id 或 kb_ids
    kb_id = question.metadata.get("kb_id") if question.metadata else None
    kb_ids = question.metadata.get("kb_ids") if question.metadata else None

    context = SearchContext(
        question=question,
        queries=[query for query in queries if query],
        filter_doc_ids=filter_doc_ids,
        metadata={
            # ...
            "kb_id": kb_id,
            "kb_ids": kb_ids,
        },
    )
    
    # ... 检索 ...

    # 融合后过滤
    if kb_ids:
        # 多知识库融合：保留属于任一选中 KB 的结果
        kb_ids_set = set(kb_ids)
        fused = [r for r in fused if r.metadata.get("kb_id") in kb_ids_set]
    elif kb_id:
        # 单知识库隔离：只保留该 KB 的结果
        fused = [r for r in fused if r.metadata.get("kb_id") == kb_id]

    return fused
```

#### 6. BM25 索引层

**文件**：`src/finlongrag/index/bm25.py`

```python
def search(
    self,
    query: str,
    top_k: int = 20,
    filter_doc_ids: set[str] | None = None,
    source: str = "bm25f",
    scoring_mode: str = "bm25f",
    kb_id: str | None = None,
    kb_ids: list[str] | None = None,  # 新增
) -> list[RetrievalResult]:
    # ...
    
    # 准备 KB 过滤集合
    kb_filter_set = None
    if kb_ids:
        kb_filter_set = set(kb_ids)
    elif kb_id:
        kb_filter_set = {kb_id}

    for idx, score in ranked:
        if score <= 0:
            continue
        chunk = self.chunks[idx]
        if filter_doc_ids and chunk.doc_id not in filter_doc_ids:
            continue
        # 多 KB 或单 KB 过滤
        if kb_filter_set:
            chunk_kb_id = chunk.metadata.get("kb_id")
            if chunk_kb_id not in kb_filter_set:
                continue
        output.append(self.result_from_chunk(chunk, float(score), source, query))
        if len(output) >= top_k:
            break
    return output
```

#### 7. BM25 搜索通道

**文件**：`src/finlongrag/retrieval/channels.py`

```python
def search(self, context: SearchContext) -> SearchChannelResult:
    # ...
    kb_id = context.metadata.get("kb_id")
    kb_ids = context.metadata.get("kb_ids")

    ranked_lists = [
        self.index.search(
            query,
            top_k=top_k_per_query,
            filter_doc_ids=context.filter_doc_ids,
            source=f"{source}:{self.name}",
            scoring_mode=scoring_mode,
            kb_id=kb_id,
            kb_ids=kb_ids,  # 传递多 KB
        )
        for query in context.queries
        if query
    ]
    # ...
```

---

## 数据流

```
前端 UI
  ↓
[融合开关关闭] → selectedKnowledgeBaseId (单选)
                    ↓
                knowledge_base_id → API
  
[融合开关打开] → selectedKnowledgeBaseIds (多选数组)
                    ↓
                kb_ids: ["id1", "id2"] → API

API (/api/v1/query/stream)
  ↓
ChatService.ask(kb_id=..., kb_ids=...)
  ↓
Pipeline.ask(kb_id=..., kb_ids=...)
  ↓
question.metadata = {"kb_id": ...} 或 {"kb_ids": [...]}
  ↓
Retriever._search_channels()
  ↓
context.metadata["kb_id"] 或 context.metadata["kb_ids"]
  ↓
BM25SearchChannel.search() / FaissSearchChannel.search()
  ↓
BM25FIndex.search(kb_id=..., kb_ids=...)
  ↓
过滤：chunk.metadata.get("kb_id") in kb_filter_set
  ↓
Retriever 融合后再过滤（三层过滤保证隔离）
  ↓
返回结果
```

---

## 测试场景

### 场景 1：单库隔离（开关关闭）
1. 关闭"融合"开关
2. 选择"金融"知识库
3. 提问："私募投资基金信息披露监督管理办法第三章第十九条的内容是什么"
4. **期望结果**：未找到相关内容（因为这是管理库的内容）

### 场景 2：多库融合（开关打开）
1. 打开"融合"开关
2. 同时选择"金融"和"管理"两个知识库
3. 提问："私募投资基金信息披露监督管理办法第三章第十九条的内容是什么"
4. **期望结果**：返回管理库的内容（因为融合了两个库）

### 场景 3：多库综合查询
1. 打开"融合"开关
2. 选择"金融"和"管理"
3. 提问："金融行业和私募基金管理有什么关系"
4. **期望结果**：融合两个库的内容，给出综合答案

---

## 修改文件清单

### 前端
- ✅ `frontend/src/views/chat/ChatPage.vue`
  - UI 组件（单选/多选切换）
  - 状态管理（`selectedKnowledgeBaseIds`）
  - 请求参数构建
  - 查询验证逻辑

### 后端
- ✅ `src/finlongrag/api/v1.py` - API 请求模型和处理
- ✅ `src/finlongrag/conversation/service.py` - ChatService 层
- ✅ `src/finlongrag/service/pipeline.py` - Pipeline 层
- ✅ `src/finlongrag/retrieval/retriever.py` - Retriever 层过滤
- ✅ `src/finlongrag/index/bm25.py` - BM25 索引层过滤
- ✅ `src/finlongrag/retrieval/channels.py` - 搜索通道传递

---

## 优势

1. **用户友好**：一个开关控制两种模式，清晰直观
2. **灵活性高**：既支持严格隔离，也支持灵活融合
3. **性能优化**：依然使用全局索引，无需为每个 KB 维护单独索引
4. **向后兼容**：保留了原有的单 KB 模式，不影响现有功能

---

## 注意事项

1. **多库模式的初始化检查**：目前多库模式跳过了 KB 初始化检查，可优化为检查所有选中的 KB 是否都已初始化
2. **FAISS 向量索引**：目前只实现了 BM25 的多 KB 支持，FAISS 层也需要类似修改（如果启用向量检索）
3. **会话记录**：conversation metadata 记录了 `kb_ids` 数组，可用于恢复会话时的 KB 选择状态
