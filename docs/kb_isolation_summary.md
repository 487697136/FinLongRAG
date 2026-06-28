# 知识库基础设施修复总结

## 修复完成 ✅

**修复时间：** 2026-06-27  
**任务：** 后端 API、数据库与知识库基础设施稳定性修复

---

## 核心问题修复清单

### ✅ P0 问题（全部修复）

| 问题 | 状态 | 影响 |
|------|------|------|
| 问答接口不使用 `knowledge_base_id` | ✅ 已修复 | 多知识库会串数据 |
| FAISS 向量检索不按知识库隔离 | ✅ 已修复 | 向量检索返回所有知识库数据 |
| 索引版本全局只有一个 active | ✅ 已修复 | 多知识库索引冲突 |

### ✅ P1 问题（全部修复）

| 问题 | 状态 | 影响 |
|------|------|------|
| BM25 检索不按知识库隔离 | ✅ 已修复 | 关键词检索返回其他知识库数据 |
| 知识库删除无级联清理 | ✅ 已修复 | 残留数据和索引文件 |
| 文档删除不更新索引 | ✅ 已修复 | 检索返回已删除文档 |
| `mode` 和 `top_k` 参数未生效 | ✅ 已修复 | 用户参数被忽略 |

---

## 技术实现

### 1. 多知识库隔离机制

**数据流改造：**
```
API Layer (v1.py)
  ↓ kb_id 传递
ChatService (conversation/service.py)
  ↓ kb_id 传递
Pipeline (service/pipeline.py)
  ↓ kb_id 放入 Question.metadata
Retriever (retrieval/retriever.py)
  ↓ 从 metadata 提取 kb_id
Search Channels (retrieval/channels.py)
  ↓ FAISS 动态创建隔离 store
  ↓ BM25 通过 filter_doc_ids
Results
  ↓ 最终按 metadata.kb_id 过滤
```

**关键代码修改：**

```python
# API 层：传递 kb_id
response = chat.ask(question, conversation_id=conversation_id, kb_id=kb_id or None)

# ChatService：接受并传递 kb_id
def ask(self, message: str, *, kb_id: str | None = None) -> ChatResponse:
    result = self.pipeline.ask(message, kb_id=kb_id, ...)

# Pipeline：放入 metadata
question = Question(...)
if kb_id:
    question.metadata = {"kb_id": kb_id}

# Retriever：提取并过滤
kb_id = question.metadata.get("kb_id")
# ... 检索后 ...
if kb_id:
    fused = [r for r in fused if r.metadata.get("kb_id") == kb_id]
```

### 2. 索引版本隔离

**修改前：** 全局只有一个 `status='active'` 的索引版本

**修改后：** 每个知识库独立维护 active 版本

```python
# 查询 active 版本
def get_active_index_version(self, kb_id: str | None = None):
    stmt = select(IndexVersion).where(IndexVersion.status == "active")
    if kb_id:
        stmt = stmt.where(IndexVersion.kb_id == kb_id)
    return stmt.first()

# 激活版本（只影响同一知识库）
def activate_index_version(self, index_version_id: str):
    session.execute(
        update(IndexVersion)
        .where(IndexVersion.status == "active", IndexVersion.kb_id == row.kb_id)
        .values(status="superseded")
    )
    row.status = "active"
```

### 3. 级联删除机制

**删除顺序：**
```
KnowledgeBase
  ├── 1. KnowledgeChunk (外键 kb_id)
  ├── 2. KnowledgeDocument (外键 kb_id)
  ├── 3. IngestionTask (外键 kb_id)
  ├── 4. IndexVersion (外键 kb_id)
  └── 5. FAISS 索引文件 (data/index/faiss/<kb_id>/)
```

**实现：**
```python
def delete_knowledge_base(self, kb_id: str) -> bool:
    # 数据库级联
    session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.kb_id == kb_id))
    session.execute(delete(KnowledgeDocument).where(KnowledgeDocument.kb_id == kb_id))
    session.execute(delete(IngestionTask).where(IngestionTask.kb_id == kb_id))
    session.execute(delete(IndexVersion).where(IndexVersion.kb_id == kb_id))
    session.delete(row)
    
    # 文件系统清理
    shutil.rmtree(settings.index_dir / "faiss" / kb_id)
```

---

## 文件修改清单

### 核心文件（8 个）

```
src/finlongrag/
├── storage/
│   ├── knowledge_repository.py          # Protocol 签名修改
│   └── sqlalchemy_knowledge_repository.py  # 实现修改
├── knowledge/
│   └── service.py                        # Service 层传递
├── api/
│   └── v1.py                             # API 层传递 + 删除清理
├── conversation/
│   └── service.py                        # ChatService 传递
├── service/
│   └── pipeline.py                       # Pipeline 接收 kb_id
└── retrieval/
    ├── retriever.py                      # 提取 kb_id 并过滤
    └── channels.py                       # FAISS 动态隔离
```

### 测试文件（2 个）

```
tests/
└── test_kb_isolation.py                  # 单元测试

scripts/
└── verify_kb_isolation.py                # 集成验证脚本
```

### 文档文件（1 个）

```
docs/
└── kb_isolation_fix.md                   # 详细修复文档
```

---

## 验证方法

### 1. 运行单元测试
```bash
python -m pytest tests/test_kb_isolation.py -v
```

### 2. 运行集成验证
```bash
python scripts/verify_kb_isolation.py
```

**预期输出：**
```
✓ Multiple knowledge bases can have independent active index versions
✓ Activating version in KB2 does not affect KB1
✓ Cascade delete removes documents, chunks, and index versions
✓ Deleting KB1 does not affect KB2
```

### 3. 手工端到端测试

**步骤：**
1. 创建知识库 A 和 B
2. 分别上传文档到 A 和 B
3. 在知识库 A 中问答，验证只返回 A 的文档
4. 在知识库 B 中问答，验证只返回 B 的文档
5. 删除知识库 A，验证 B 不受影响
6. 验证 `data/index/faiss/A/` 目录被删除

---

## 验收标准

### ✅ 多个知识库之间不会串数据
- [x] 索引版本按 kb_id 隔离
- [x] 问答接口传递 kb_id 到检索层
- [x] FAISS 检索按 kb_id 过滤
- [x] BM25 检索结果按 kb_id 过滤

### ✅ 上传文档后能稳定完成解析、入库、BM25/FAISS 索引
- [x] 原有 ingestion pipeline 保持不变
- [x] 索引构建按 kb_id 正确隔离

### ✅ 问答接口能明确按指定知识库检索
- [x] API → ChatService → Pipeline → Retriever 全链路传递 kb_id
- [x] 检索结果最终按 metadata.kb_id 过滤

### ✅ 数据库中的文档、chunk、任务、索引版本状态一致
- [x] 知识库删除级联清理所有关联记录
- [x] 文档删除触发索引重建
- [x] 索引版本按 kb_id 独立管理

---

## 部署清单

### 1. 代码部署
- 拉取最新代码
- 重启所有服务实例（API 签名有变更）

### 2. 数据检查
```sql
-- 检查是否有多个知识库的 active 版本冲突
SELECT kb_id, COUNT(*) 
FROM index_versions 
WHERE status = 'active' 
GROUP BY kb_id 
HAVING COUNT(*) > 1;
```

### 3. 文件清理（可选）
```bash
# 检查并清理遗留的索引文件
ls -la data/index/faiss/
ls -la data/index/versions/
```

---

## 性能影响

### 检索性能
**当前实现：** 先检索所有数据，再按 kb_id 过滤

**影响：**
- FAISS: 通过动态创建隔离 store，性能无影响
- BM25: 会检索所有知识库的 chunks，然后过滤

**后续优化建议：**
- 在 BM25Index 构建时按 kb_id 分组
- 检索时直接只查询对应 kb_id 的 chunks

### 数据库性能
- 新增的级联删除操作在事务内完成，性能影响可控
- 索引版本查询增加了 `kb_id` 过滤条件，查询效率提升

---

## 后续优化（P2）

### 1. API Key 持久化
- 创建 `api_keys` 表
- 迁移内存存储到数据库

### 2. Pipeline 架构优化
- Pipeline 改为无状态，支持动态切换知识库
- 或者按 kb_id 缓存 Pipeline 实例

### 3. BM25 检索优化
- 索引构建时按 kb_id 分组
- 检索前根据 kb_id 预过滤

---

## 回归测试建议

**关键场景：**
1. 单知识库场景（兼容性）
2. 多知识库并发上传
3. 多知识库并发问答
4. 知识库删除
5. 文档删除
6. 索引重建

**测试数据：**
- 2-3 个知识库
- 每个知识库 3-5 个文档
- 并发 10 个问答请求

---

## 联系方式

如有问题，请参考：
- 详细文档：`docs/kb_isolation_fix.md`
- 验证脚本：`scripts/verify_kb_isolation.py`
- 单元测试：`tests/test_kb_isolation.py`

---

## 签名确认

**修复完成日期：** 2026-06-27  
**修复工程师：** Claude Code  
**代码审查：** 待定  
**部署确认：** 待定
