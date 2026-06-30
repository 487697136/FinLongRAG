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
            <span class="msg-ai-sender">知源</span>
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
              <span>{{ sourcesSummaryLabel(turn.sources) }}</span>
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
              <div v-if="sourcesOpenMap[turn.id]" class="source-chips">
                <span
                  v-for="(src, idx) in deduplicateSources(turn.sources)"
                  :key="src._dedupeKey"
                  class="source-chip"
                  :title="src._tooltip"
                >
                  {{ src._label }}
                </span>
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
  max-height: 200px;
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
    if (entry._bestScore > 0) parts.push(`相关度: ${(entry._bestScore * 100).toFixed(0)}%`)
    return { ...entry, _tooltip: parts.join(' | ') }
  })
}

/**
 * Summary label for the sources toggle button.
 * e.g. "引用来源（2 篇文档，共 8 段）" or "引用来源（1 篇文档）"
 */
const sourcesSummaryLabel = (sources) => {
  if (!sources?.length) return '引用来源'
  const deduped = deduplicateSources(sources)
  const docCount = deduped.length
  const chunkCount = sources.length
  if (docCount === chunkCount) {
    return `引用来源（${docCount}）`
  }
  return `引用来源（${docCount} 篇文档，共 ${chunkCount} 段）`
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
      local: 'local',
      global: 'global',
      global_local: 'global_local',
      graph_local: 'local',
      graph_global: 'global',
      graph_hybrid: 'global_local',
      llm_only: 'llm_only'
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

  if (src?.score != null) parts.push(`相关度: ${(src.score * 100).toFixed(0)}%`)
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

