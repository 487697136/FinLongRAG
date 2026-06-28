# 知识库隔离修复 - 最终检查清单

## 代码修改确认

### ✅ 数据库层
- [x] `knowledge_repository.py` - Protocol 签名更新
- [x] `sqlalchemy_knowledge_repository.py` - 实现更新
  - [x] `get_active_index_version(kb_id)` 支持按知识库查询
  - [x] `activate_index_version()` 只更新同一知识库的旧版本
  - [x] `delete_knowledge_base()` 级联删除 chunks/documents/tasks/versions
  - [x] `delete_document()` 级联删除 chunks

### ✅ 服务层
- [x] `knowledge/service.py` - 传递 kb_id 参数
- [x] `conversation/service.py` - 接受并传递 kb_id
- [x] `service/pipeline.py` - 接受 kb_id 并放入 Question.metadata

### ✅ 检索层
- [x] `retrieval/retriever.py` - 从 metadata 提取 kb_id 并过滤结果
- [x] `retrieval/channels.py` - FaissSearchChannel 动态创建隔离 store

### ✅ API 层
- [x] `api/v1.py` - 多处修改
  - [x] `query_stream()` 传递 kb_id 到 chat.ask()
  - [x] `knowledge_base_stats()` 按 kb_id 查询 active version
  - [x] `_kb_payload()` 按 kb_id 查询 active version
  - [x] `delete_knowledge_base()` 清理 FAISS 目录
  - [x] `delete_document()` 触发索引重建

---

## 测试文件创建

### ✅ 单元测试
- [x] `tests/test_kb_isolation.py`
  - [x] test_index_version_isolation - 验证多知识库索引版本隔离
  - [x] test_knowledge_base_delete_cascade - 验证级联删除

### ✅ 集成验证
- [x] `scripts/verify_kb_isolation.py`
  - [x] 创建两个知识库
  - [x] 创建独立的索引版本
  - [x] 验证隔离性
  - [x] 验证级联删除

---

## 文档创建

### ✅ 详细文档
- [x] `docs/kb_isolation_fix.md` - 完整修复文档
  - [x] 问题诊断
  - [x] 修复方案
  - [x] 技术架构
  - [x] 验收标准
  - [x] 部署注意事项

### ✅ 总结文档
- [x] `docs/kb_isolation_summary.md` - 修复总结
  - [x] 问题清单
  - [x] 技术实现
  - [x] 验证方法
  - [x] 部署清单

### ✅ 检查清单
- [x] `docs/kb_isolation_checklist.md` - 本文件

---

## 代码质量检查

### ✅ 编译检查
```bash
python -m compileall -q src scripts tests
```
- [x] 无编译错误

### ⚠️ 代码风格检查
```bash
python -m ruff check src/finlongrag
```
- [x] ruff 未安装（可选）

---

## 核心功能验证

### 待验证：索引版本隔离
```python
# 创建 KB1 和 KB2
# 为 KB1 创建并激活 version1
# 为 KB2 创建并激活 version2
# 验证：KB1 的 active version 是 version1
# 验证：KB2 的 active version 是 version2
```

### 待验证：问答隔离
```python
# 上传文档到 KB1
# 上传文档到 KB2
# 在 KB1 中问答，验证只返回 KB1 的结果
# 在 KB2 中问答，验证只返回 KB2 的结果
```

### 待验证：级联删除
```python
# 创建 KB1，上传文档，构建索引
# 删除 KB1
# 验证：数据库中 KB1 的所有记录被删除
# 验证：data/index/faiss/KB1/ 目录被删除
```

### 待验证：文档删除
```python
# 在 KB1 中删除一个文档
# 验证：索引重建任务被触发
# 验证：重建后的索引不包含该文档
```

---

## 部署前检查

### ✅ 代码准备
- [x] 所有修改已完成
- [x] 代码编译通过
- [x] 测试文件已创建
- [x] 文档已完善

### 待完成：数据库检查
- [ ] 检查现有数据库中的 index_versions 表
- [ ] 确认每个 kb_id 只有一个 active 版本
- [ ] 如有冲突，手动修正

### 待完成：备份
- [ ] 备份数据库
- [ ] 备份 data/index/ 目录

### 待完成：部署
- [ ] 拉取代码
- [ ] 重启服务
- [ ] 运行验证脚本
- [ ] 执行手工测试

---

## 回归测试清单

### 基础功能
- [ ] 创建知识库
- [ ] 上传文档
- [ ] 文档解析和 chunk
- [ ] 索引构建（BM25 + FAISS）
- [ ] 问答功能
- [ ] 会话管理

### 多知识库隔离
- [ ] 创建 2 个知识库
- [ ] 分别上传文档
- [ ] 在 KB1 中问答，只返回 KB1 的结果
- [ ] 在 KB2 中问答，只返回 KB2 的结果
- [ ] 切换知识库问答，结果正确切换

### 删除功能
- [ ] 删除文档，索引自动重建
- [ ] 删除知识库，数据和文件完全清理
- [ ] 删除不影响其他知识库

### 索引管理
- [ ] 重建索引
- [ ] 多个知识库同时有 active 索引版本
- [ ] 激活旧版本索引

---

## 性能测试

### 建议测试
- [ ] 单知识库 + 10 并发问答
- [ ] 3 知识库 + 30 并发问答（跨知识库）
- [ ] 索引构建耗时（单知识库 100 文档）
- [ ] 删除耗时（知识库包含 100 文档）

### 预期性能
- 问答响应时间：< 2 秒
- 索引构建：< 1 秒/文档
- 删除操作：< 5 秒

---

## 已知问题和限制

### 当前实现的局限
1. **BM25 检索未完全隔离**
   - 当前：检索所有 chunks，再过滤
   - 理想：只检索指定 kb_id 的 chunks

2. **Pipeline 不支持动态切换**
   - 当前：初始化时固定加载索引
   - 理想：无状态设计，支持动态加载

3. **API Key 未持久化**
   - 当前：存储在内存中
   - 理想：存储在数据库中

### 后续优化方向
- P2-1: BM25 索引按 kb_id 分组
- P2-2: Pipeline 架构重构
- P2-3: API Key 持久化

---

## 风险评估

### 低风险
- [x] 新增参数向后兼容
- [x] 数据库操作在事务内
- [x] 级联删除有确认步骤

### 中风险
- [ ] 现有数据可能有索引版本冲突 → 需要检查
- [ ] 检索性能可能下降 → 需要监控

### 高风险
- 无

---

## 回滚计划

### 如果出现问题
1. **代码回滚**
   ```bash
   git checkout <previous-commit>
   ```

2. **数据库回滚**
   - 恢复备份的数据库

3. **索引回滚**
   - 恢复备份的 data/index/ 目录

### 回滚验证
- [ ] 服务启动正常
- [ ] 问答功能正常
- [ ] 索引构建正常

---

## 签名确认

### 开发阶段
- [x] 代码修改完成 - Claude Code - 2026-06-27
- [x] 单元测试创建 - Claude Code - 2026-06-27
- [x] 文档完成 - Claude Code - 2026-06-27

### 待完成
- [ ] 代码审查 - __________ - ____-__-__
- [ ] 集成测试通过 - __________ - ____-__-__
- [ ] 部署到测试环境 - __________ - ____-__-__
- [ ] 性能测试通过 - __________ - ____-__-__
- [ ] 部署到生产环境 - __________ - ____-__-__

---

## 附录

### 修改的文件列表
```
src/finlongrag/storage/knowledge_repository.py
src/finlongrag/storage/sqlalchemy_knowledge_repository.py
src/finlongrag/knowledge/service.py
src/finlongrag/api/v1.py
src/finlongrag/conversation/service.py
src/finlongrag/service/pipeline.py
src/finlongrag/retrieval/retriever.py
src/finlongrag/retrieval/channels.py
tests/test_kb_isolation.py (新增)
scripts/verify_kb_isolation.py (新增)
docs/kb_isolation_fix.md (新增)
docs/kb_isolation_summary.md (新增)
docs/kb_isolation_checklist.md (新增)
```

### 关键代码行数统计
- 修改代码：约 200 行
- 新增测试：约 150 行
- 新增文档：约 1000 行

### 预计影响范围
- 核心模块：8 个文件
- 测试覆盖：2 个新测试文件
- 文档更新：3 个新文档
