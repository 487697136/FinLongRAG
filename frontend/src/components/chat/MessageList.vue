<template>
  <div class="messages">
    <div v-for="turn in turns" :key="turn.id" class="message-group">
      <!-- 用户消息 -->
      <div class="message message--user">
        <div class="msg-avatar msg-avatar--user">你</div>
        <div class="msg-user-bubble">{{ turn.question }}</div>
      </div>

      <!-- AI 回答 -->
      <div class="message message--ai">
        <div class="msg-avatar msg-avatar--ai">
          <slot name="ai-avatar" />
        </div>
        <div class="msg-ai-content">
          <div class="msg-ai-header">
            <span class="msg-ai-sender">FinLongRAG</span>
            <span v-if="turn.created_at && !turn.streaming" class="msg-ai-time">
              {{ formatTime(turn.created_at) }}
            </span>
          </div>

          <div class="msg-ai-bubble" :class="{ 'msg-ai-bubble--streaming': turn.streaming }">
            <!-- 流式阶段：pre 展示，保留原始格式，有打字光标 -->
            <template v-if="turn.streaming">
              <div v-if="turn.streamStatus && !turn.answer" class="stream-status">
                <span class="stream-status__dots">
                  <span class="thinking-dot" />
                  <span class="thinking-dot" />
                  <span class="thinking-dot" />
                </span>
                <span class="stream-status__label">{{ streamStatusLabel(turn.streamStatus) }}</span>
              </div>
              <div v-else-if="!turn.answer" class="thinking-indicator">
                <span class="thinking-dot" />
                <span class="thinking-dot" />
                <span class="thinking-dot" />
              </div>
              <pre v-if="turn.answer" class="msg-ai-streaming">{{ turn.answer }}</pre>
              <span v-if="turn.answer || !turn.streamStatus" class="typing-caret" />
            </template>

            <!-- 完成后：Markdown 渲染 -->
            <div v-else-if="turn.answer" class="markdown-body" v-html="renderMarkdown(turn.answer)" />

            <!-- 复制按钮：只在完成且有内容时显示 -->
            <button
              v-if="!turn.streaming && turn.answer && !turn.is_error"
              class="msg-copy-btn"
              :class="{ 'msg-copy-btn--copied': copiedId === turn.id }"
              type="button"
              :title="copiedId === turn.id ? '已复制' : '复制回答'"
              @click="copyAnswer(turn)"
            >
              <svg v-if="copiedId !== turn.id" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
              </svg>
              <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
            </button>
          </div>

          <!-- 引用来源 -->
          <div v-if="turn.sources?.length" class="msg-sources">
            <button
              class="msg-sources__toggle"
              type="button"
              @click="toggleSources(turn.id)"
            >
              <slot name="source-icon" />
              <span>{{ sourcesSummaryLabel(turn) }}</span>
              <svg
                class="msg-sources__chevron"
                :class="{ 'msg-sources__chevron--open': sourcesOpenMap[turn.id] }"
                width="12" height="12" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" stroke-width="2.5"
              >
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </button>
            <transition name="sources-expand">
              <div v-if="sourcesOpenMap[turn.id]" class="source-evidence-list">
                <article
                  v-for="(src, idx) in visibleSources(turn)"
                  :key="idx"
                  class="source-evidence-card"
                  :title="getSourceTooltip(src)"
                >
                  <div class="source-evidence-card__header">
                    <div class="source-evidence-card__title">
                      <span v-if="src?._evidenceIndex" class="source-evidence-card__cite">E{{ src._evidenceIndex }}</span>
                      {{ getSourceTitle(src, idx) }}
                    </div>
                    <span v-if="formatSourceScore(src)" class="source-evidence-card__score">{{ formatSourceScore(src) }}</span>
                  </div>
                  <div class="source-evidence-card__meta">
                    <span v-if="src?.source">检索来源：{{ normalizeSourceLabel(src.source) }}</span>
                    <span v-if="src?.chunk_id">片段 #{{ src.chunk_id }}</span>
                    <span v-if="src?.page != null">页码 {{ src.page }}</span>
                  </div>
                  <p v-if="src?.content || src?.text || src?.snippet" class="source-evidence-card__snippet">
                    {{ src.content || src.text || src.snippet }}
                  </p>
                </article>
              </div>
            </transition>
          </div>

          <!-- 元信息行 -->
          <div v-if="!turn.streaming" class="msg-meta-row">
            <span class="msg-mode-badge">{{ getModeLabel(turn.mode || turn.requested_mode) }}</span>
            <span v-if="turn.response_time" class="msg-time-tag">{{ turn.response_time.toFixed(2) }}s</span>
            <span v-if="turn.token_count" class="msg-time-tag">{{ turn.token_count }} tokens</span>
            <span
              v-if="turn.retrieval_summary?.planned_modes?.length"
              class="msg-time-tag"
            >
              路由：{{ turn.retrieval_summary.planned_modes.join(' + ') }}
            </span>
          </div>

          <!-- 错误操作 -->
          <div v-if="turn.is_error" class="msg-error-actions">
            <slot name="error-actions" :turn="turn" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 来源展开/收起过渡动画 */
.sources-expand-enter-active,
.sources-expand-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease, max-height 0.25s ease;
  overflow: hidden;
}

.sources-expand-enter-from,
.sources-expand-leave-to {
  opacity: 0;
  transform: translateY(-4px);
  max-height: 0 !important;
}

.sources-expand-enter-to,
.sources-expand-leave-from {
  max-height: 520px;
}

.msg-sources__toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  border: 1px solid var(--brand-soft-border);
  border-radius: 999px;
  background: var(--surface-soft);
  color: var(--brand-700);
  font-size: 12px;
  font-weight: 700;
}

.msg-sources__chevron {
  transition: transform 0.2s ease;
}

.msg-sources__chevron--open {
  transform: rotate(180deg);
}

.source-evidence-list {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}

.source-evidence-card {
  padding: 14px 15px;
  border-radius: 14px;
  border: 1px solid var(--border-color);
  background: linear-gradient(180deg, #ffffff, var(--surface-muted));
  box-shadow: var(--shadow-subtle);
}

.source-evidence-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.source-evidence-card__title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-1);
}

.source-evidence-card__score {
  flex-shrink: 0;
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.08);
  color: var(--brand-700);
  font-size: 11px;
  font-weight: 700;
}

.source-evidence-card__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  margin-bottom: 10px;
  color: var(--text-4);
  font-size: 12px;
}

.source-evidence-card__snippet {
  margin: 0;
  color: var(--text-2);
  font-size: 13px;
  line-height: 1.72;
  white-space: pre-wrap;
}
</style>

<script setup>
import { reactive, ref } from 'vue'

const props = defineProps({
  turns: { type: Array, default: () => [] },
  renderMarkdown: { type: Function, required: true },
  getModeLabel: { type: Function, required: true },
  getSourceTitle: { type: Function, required: true }
})

const copiedId = ref(null)
const sourcesOpenMap = reactive({})

const copyAnswer = async (turn) => {
  if (!turn.answer) return
  try {
    await navigator.clipboard.writeText(turn.answer)
    copiedId.value = turn.id
    setTimeout(() => { copiedId.value = null }, 2000)
  } catch {
    // 降级：手动创建 textarea
    const el = document.createElement('textarea')
    el.value = turn.answer
    document.body.appendChild(el)
    el.select()
    document.execCommand('copy')
    document.body.removeChild(el)
    copiedId.value = turn.id
    setTimeout(() => { copiedId.value = null }, 2000)
  }
}

const toggleSources = (turnId) => {
  sourcesOpenMap[turnId] = !sourcesOpenMap[turnId]
}

const STREAM_STATUS_LABELS = {
  retrieving: '检索知识库中…',
  verifying: '核验选项中…',
  generating: '生成回答中…'
}

const streamStatusLabel = (status) => STREAM_STATUS_LABELS[status] || '处理中…'

const MAX_VISIBLE_SOURCES = 8

const citationIndexes = (answer) => {
  const indexes = new Set()
  const text = String(answer || '')
  for (const match of text.matchAll(/\[E(\d+)\]/g)) {
    indexes.add(Number(match[1]))
  }
  return indexes
}

const sourceWithEvidenceIndex = (src, idx) => ({
  ...src,
  _evidenceIndex: idx + 1
})

const visibleSources = (turn) => {
  const sources = Array.isArray(turn?.sources) ? turn.sources : []
  if (!sources.length) return []

  const cited = citationIndexes(turn?.answer)
  const indexed = sources.map(sourceWithEvidenceIndex)
  if (cited.size) {
    const citedSources = indexed.filter((src) => cited.has(src._evidenceIndex))
    if (citedSources.length) return citedSources
  }
  return indexed.slice(0, MAX_VISIBLE_SOURCES)
}

/**
 * Group raw evidence chunks by document, returning one entry per unique document.
 * Each returned object has: _dedupeKey, _label, _tooltip, _chunkCount.
 */
const deduplicateSources = (sources) => {
  if (!sources?.length) return []
  const docMap = new Map()

  sources.forEach((src, idx) => {
    // Derive a stable document key from doc_id > title > source > fallback index
    const docKey = String(src?.doc_id || src?.title || src?.name || src?.source || idx)
    // Human-readable label for the document
    const label = src?.title || src?.name || src?.doc_id || src?.source || `来源 ${idx + 1}`

    // page can be top-level or inside metadata
    const page = src?.page ?? src?.metadata?.page ?? null

    if (!docMap.has(docKey)) {
      docMap.set(docKey, {
        _dedupeKey: docKey,
        _label: label,
        _chunkCount: 1,
        _pages: page != null ? [page] : [],
        _bestScore: src?.score ?? 0,
        _raw: src,
      })
    } else {
      const entry = docMap.get(docKey)
      entry._chunkCount += 1
      if (page != null && !entry._pages.includes(page)) {
        entry._pages.push(page)
      }
      if ((src?.score ?? 0) > entry._bestScore) entry._bestScore = src.score
    }
  })

  // Build tooltip and finalize labels
  return Array.from(docMap.values()).map((entry) => {
    const parts = [entry._label]
    if (entry._chunkCount > 1) parts.push(`${entry._chunkCount} 段`)
    if (entry._pages.length) {
      const sorted = [...entry._pages].sort((a, b) => a - b)
      const pagesStr = sorted.length > 3
        ? `第 ${sorted[0]}–${sorted[sorted.length - 1]} 页`
        : `第 ${sorted.join('、')} 页`
      parts.push(pagesStr)
    }
    if (entry._bestScore > 0) parts.push(`排序分: ${formatRawScore(entry._bestScore)}`)
    return { ...entry, _tooltip: parts.join(' | ') }
  })
}

/**
 * Summary label for the sources toggle button.
 * e.g. "引用来源（2 篇文档，共 8 段）" or "引用来源（1 篇文档）"
 */
const sourcesSummaryLabel = (turn) => {
  const sources = Array.isArray(turn?.sources) ? turn.sources : []
  if (!sources?.length) return '引用来源'
  const deduped = deduplicateSources(sources)
  const docCount = deduped.length
  const chunkCount = sources.length
  const visibleCount = visibleSources(turn).length
  const citedCount = citationIndexes(turn?.answer).size
  if (citedCount && visibleCount) {
    return `引用来源（答案引用 ${visibleCount} 段 / 共 ${chunkCount} 段证据）`
  }
  if (chunkCount > MAX_VISIBLE_SOURCES) {
    return `引用来源（展示前 ${MAX_VISIBLE_SOURCES} 段 / 共 ${chunkCount} 段证据）`
  }
  if (docCount === chunkCount) return `引用来源（${docCount}）`
  return `引用来源（${docCount} 篇文档，共 ${chunkCount} 段证据）`
}

const normalizeSourceLabel = (source) => {
  const v = String(source || '').trim()
  const map = {
    naive: '向量检索',
    vector: '向量检索',
    bm25: '关键词检索',
    keyword: '关键词检索',
    auto: '混合检索',
    'rrf:bm25': '融合排序：关键词',
    'rrf:faiss': '融合排序：向量',
    'rrf:vector': '融合排序：向量'
  }
  return map[v] || v || '未知来源'
}

const formatRawScore = (score) => {
  const value = Number(score)
  if (!Number.isFinite(value)) return ''
  if (value >= 100) return value.toFixed(0)
  if (value >= 10) return value.toFixed(1)
  if (value >= 1) return value.toFixed(2)
  return value.toFixed(3)
}

const formatSourceScore = (src) => {
  const rerankScore = Number(src?.metadata?.rerank_score)
  if (Number.isFinite(rerankScore)) {
    if (rerankScore >= 0 && rerankScore <= 1) return `重排相关性 ${(rerankScore * 100).toFixed(0)}%`
    return `重排分 ${formatRawScore(rerankScore)}`
  }

  const score = Number(src?.score)
  if (!Number.isFinite(score)) return ''
  const source = String(src?.source || '')
  if (source.startsWith('rrf:')) return `融合排序分 ${formatRawScore(score)}`
  if (score >= 0 && score <= 1) return `检索分 ${formatRawScore(score)}`
  return `检索分 ${formatRawScore(score)}`
}

const getSourceTooltip = (src) => {
  const normalize = (s) => {
    const v = String(s || '').trim()
    if (!v) return ''
    const map = {
      naive: 'vector',
      vector: 'vector',
      bm25: 'bm25',
      keyword: 'bm25',
      auto: 'auto'
    }
    return map[v] || v
  }

  const parts = []
  if (src?.title) parts.push(src.title)

  if (Array.isArray(src?.sources) && src.sources.length) {
    const unique = [...new Set(src.sources.map(normalize).filter(Boolean))]
    if (unique.length) parts.push(unique.join('+'))
  } else if (src?.source && src.source !== src?.title) {
    parts.push(normalize(src.source))
  }

  const scoreLabel = formatSourceScore(src)
  if (scoreLabel) parts.push(scoreLabel)
  return parts.join(' | ')
}

const formatTime = (isoStr) => {
  if (!isoStr) return ''
  const d = new Date(isoStr)
  if (isNaN(d.getTime())) return ''
  const now = new Date()
  const diffMs = now - d
  if (diffMs < 60000) return '刚刚'
  if (diffMs < 3600000) return `${Math.floor(diffMs / 60000)} 分钟前`
  if (diffMs < 86400000) {
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
</script>
