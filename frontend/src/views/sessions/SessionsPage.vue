<template>
  <div class="sessions-page page-shell">
    <PageHeader
      title="会话中心"
      description="统一查看真实会话记录，并基于已保存的上下文继续处理问题。"
      badge="会话记录"
    >
      <template #actions>
        <n-space>
          <n-button quaternary :loading="loading" @click="loadSessions">刷新列表</n-button>
          <n-button type="primary" @click="handleCreateConversation">新建会话</n-button>
        </n-space>
      </template>
    </PageHeader>

    <div class="sessions-overview-grid">
      <InfoCard label="会话总数" :value="sessionRecordList.length" caption="当前账户下的全部会话记录" tone="info" />
      <InfoCard label="累计轮次" :value="totalTurns" caption="所有会话累计保存的问答轮次" tone="muted" />
      <InfoCard label="知识库覆盖" :value="activeKnowledgeBaseCount" caption="参与会话的知识库数量" tone="muted" />
    </div>

    <FilterToolbar>
      <template #filters>
        <n-input
          v-model:value="searchKeyword"
          clearable
          placeholder="搜索会话标题"
          style="min-width: 280px; flex: 1"
        >
          <template #prefix>
            <n-icon :component="SearchOutline" />
          </template>
        </n-input>

        <n-select
          v-model:value="selectedKnowledgeBaseId"
          :options="knowledgeBaseFilterOptions"
          style="width: 220px"
        />
      </template>

      <template #summary>
        <div class="toolbar-summary">
          <span>筛选结果 {{ filteredSessionList.length }} 条</span>
        </div>
      </template>
    </FilterToolbar>

    <div class="sessions-list-wrap">
      <n-spin :show="loading">
        <template v-if="groupedSessionList.length">
          <div v-for="sessionGroup in groupedSessionList" :key="sessionGroup.label" class="session-group">
            <div class="session-group__label">{{ sessionGroup.label }}</div>
            <div class="session-card-grid">
              <div v-for="item in sessionGroup.items" :key="item.id" class="session-card" @click="goChat(item)">
                <div class="session-card__body">
                  <h3 class="session-card__title">{{ item.title || '未命名会话' }}</h3>
                  <div class="session-card__meta">
                    <span>{{ resolveKnowledgeBaseName(item.knowledge_base_id) }}</span>
                    <span class="session-card__sep">·</span>
                    <span>{{ item.turn_count }} 轮</span>
                    <span class="session-card__sep">·</span>
                    <span>{{ formatDateTime(item.updated_at || item.last_active_at) }}</span>
                  </div>
                </div>
                <div class="session-card__actions">
                  <button class="session-card__btn" title="查看详情" @click.stop="showSessionDetail(item)">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                  </button>
                  <button class="session-card__btn session-card__btn--danger" title="删除" @click.stop="confirmDeleteSession(item.id)">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </template>
        <n-empty v-else description="暂无会话记录，去问答页发起第一次对话吧" style="padding: 48px 0" />
      </n-spin>
    </div>

    <!-- 详情弹窗 -->
    <n-modal v-model:show="showDetailModal" preset="card" style="max-width: 680px; width: 90vw;" :mask-closable="true" closable>
      <template #header><span style="font-weight:700;font-size:17px;">会话详情</span></template>
      <template v-if="detailSession">
        <div style="margin-bottom:18px;padding-bottom:16px;border-bottom:1px solid var(--border-color);">
          <div style="font-size:16px;font-weight:700;color:var(--text-1);margin-bottom:8px;">{{ detailSession.title }}</div>
          <div style="display:flex;gap:16px;font-size:13px;color:var(--text-4);flex-wrap:wrap;">
            <span>{{ resolveKnowledgeBaseName(detailSession.knowledge_base_id) }}</span>
            <span>{{ detailSession.turn_count }} 轮对话</span>
            <span>{{ formatDateTime(detailSession.last_active_at) }}</span>
          </div>
        </div>
        <n-spin :show="detailLoading">
          <div v-if="detailSessionTurns.length" class="turn-preview-list">
            <div v-for="(turn, idx) in detailSessionTurns" :key="idx" class="turn-item">
              <div class="turn-item__label">问题 {{ idx + 1 }}</div>
              <div class="turn-item__text">{{ turn.question }}</div>
              <div class="turn-item__label" style="margin-top:14px;">回答</div>
              <div class="turn-item__text turn-item__text--answer">{{ turn.answer?.slice(0, 300) || '...' }}{{ turn.answer?.length > 300 ? '...' : '' }}</div>
              <div class="turn-item__footer">
                <span>{{ getModeLabel(turn.mode || turn.requested_mode) }}</span>
                <span>{{ formatDateTime(turn.created_at) }}</span>
              </div>
            </div>
          </div>
          <n-empty v-else description="暂无对话内容" style="padding:28px 0" />
        </n-spin>
      </template>
    </n-modal>

    <!-- 删除确认弹窗 -->
    <n-modal
      v-model:show="showDeleteConfirm"
      preset="dialog"
      type="error"
      title="删除会话"
      positive-text="确认删除"
      negative-text="取消"
      @positive-click="handleDeleteSession"
      @negative-click="showDeleteConfirm = false"
    >
      <template #default>
        <p>确定要删除此会话吗？会话记录将被永久清除，无法恢复。</p>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import { useRouter } from 'vue-router'
import {
  NButton,
  NEmpty,
  NIcon,
  NInput,
  NModal,
  NSpace,
  NSelect,
  NSpin,
  useMessage
} from 'naive-ui'
import { SearchOutline, TrashOutline } from '@vicons/ionicons5'
import {
  deleteConversationSession,
  getConversationSessionDetail,
  listConversationSessions,
} from '@/api/api'
import FilterToolbar from '@/components/common/FilterToolbar.vue'
import InfoCard from '@/components/common/InfoCard.vue'
import SectionCard from '@/components/common/SectionCard.vue'
import PageHeader from '@/components/layout/PageHeader.vue'
import { formatDateTime, formatRelativeGroup } from '@/utils/formatters'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBase'

const router = useRouter()
const message = useMessage()
const kbStore = useKnowledgeBaseStore()

const sessionRecordList = ref([])
const knowledgeBaseList = computed(() => kbStore.list)
const selectedSessionDetail = ref(null)
const searchKeyword = ref('')
const selectedKnowledgeBaseId = ref('all')
const selectedSessionId = ref('')
const loading = ref(false)
const showDeleteConfirm = ref(false)
const pendingDeleteSessionId = ref(null)
const detailLoading = ref(false)
const showDetailModal = ref(false)
const detailSession = ref(null)
const detailSessionTurns = ref([])

const showSessionDetail = async (session) => {
  detailSession.value = session
  showDetailModal.value = true
  detailLoading.value = true
  try {
    const detail = await getConversationSessionDetail(session.id)
    detailSessionTurns.value = detail.turns || []
  } catch {
    detailSessionTurns.value = []
  } finally {
    detailLoading.value = false
  }
}

const knowledgeBaseFilterOptions = computed(() => [
  { label: '全部知识库', value: 'all' },
  ...knowledgeBaseList.value.map((kbItem) => ({ label: kbItem.name, value: String(kbItem.id) }))
])

const filteredSessionList = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase()

  return sessionRecordList.value.filter((sessionItem) => {
    if (selectedKnowledgeBaseId.value !== 'all' && String(sessionItem.knowledge_base_id) !== selectedKnowledgeBaseId.value) {
      return false
    }
    if (!keyword) {
      return true
    }
    return String(sessionItem.title || '').toLowerCase().includes(keyword)
  })
})

const groupedSessionList = computed(() => {
  const groupOrder = ['今天', '近 7 天', '更早']
  return groupOrder
    .map((groupLabel) => ({
      label: groupLabel,
      items: filteredSessionList.value.filter((sessionItem) => formatRelativeGroup(sessionItem.last_active_at || sessionItem.updated_at) === groupLabel)
    }))
    .filter((groupItem) => groupItem.items.length > 0)
})

const selectedSessionRecord = computed(() => {
  return sessionRecordList.value.find((sessionItem) => String(sessionItem.id) === String(selectedSessionId.value)) || null
})

const totalTurns = computed(() => sessionRecordList.value.reduce((sum, item) => sum + Number(item.turn_count || 0), 0))
const activeKnowledgeBaseCount = computed(() => new Set(sessionRecordList.value.map((item) => item.knowledge_base_id).filter(Boolean)).size)

const resolveKnowledgeBaseName = (kbId) => {
  return kbStore.list.find((kbItem) => kbItem.id === kbId)?.name || `知识库 ${kbId}`
}

const loadSessions = async () => {
  loading.value = true
  try {
    const [sessions] = await Promise.all([
      listConversationSessions({ limit: 100 }),
      kbStore.fetchList()
    ])
    sessionRecordList.value = sessions
    if (!selectedSessionId.value && sessions.length) {
      selectedSessionId.value = String(sessions[0].id)
    }
  } catch (error) {
    message.error(error.response?.data?.detail || '加载会话失败')
  } finally {
    loading.value = false
  }
}

const loadSessionDetail = async (sessionId) => {
  if (!sessionId) {
    selectedSessionDetail.value = null
    return
  }
  detailLoading.value = true
  try {
    selectedSessionDetail.value = await getConversationSessionDetail(sessionId)
  } catch (error) {
    selectedSessionDetail.value = null
    message.error(error.response?.data?.detail || '加载会话详情失败')
  } finally {
    detailLoading.value = false
  }
}

const goChat = (session) => {
  router.push({ path: '/chat', query: { session: String(session.id), kb: String(session.knowledge_base_id) } })
}

const getModeLabel = (mode) => {
  const m = { naive: '文档检索', auto: '混合检索' }
  return m[mode] || mode || '--'
}

function confirmDeleteSession(sessionId) {
  pendingDeleteSessionId.value = sessionId
  showDeleteConfirm.value = true
}

const handleDeleteSession = async () => {
  const sessionId = pendingDeleteSessionId.value
  if (!sessionId) return
  try {
    await deleteConversationSession(sessionId)
    showDeleteConfirm.value = false
    message.success('会话已删除')
    await loadSessions()
    window.dispatchEvent(new CustomEvent('session-changed'))
    if (selectedSessionId.value === String(sessionId)) {
      const nextSessionId = sessionRecordList.value[0]?.id
      selectedSessionId.value = nextSessionId ? String(nextSessionId) : ''
    }
  } catch (error) {
    message.error(error.response?.data?.detail || '删除会话失败')
  } finally {
    pendingDeleteSessionId.value = null
  }
}

const handleCreateConversation = async () => {
  await router.push('/chat')
}

watch(selectedSessionId, async (sessionId) => {
  if (sessionId) {
    await loadSessionDetail(sessionId)
  } else {
    selectedSessionDetail.value = null
  }
})

onMounted(async () => {
  await loadSessions()
  window.addEventListener('session-changed', loadSessions)
})

onUnmounted(() => {
  window.removeEventListener('session-changed', loadSessions)
})
</script>

<style scoped>
.sessions-overview-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.toolbar-summary {
  display: flex; flex-wrap: wrap; gap: 16px;
  font-size: 13px; color: var(--text-4);
}

.sessions-list-wrap { margin-top: 4px; }

.session-group { margin-top: 28px; }
.session-group:first-child { margin-top: 0; }

.session-group__label {
  font-size: 13px; font-weight: 700; color: var(--text-3);
  margin-bottom: 12px; padding-left: 2px;
  text-transform: uppercase; letter-spacing: 0.5px;
}

.session-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 12px;
}

.session-card {
  display: flex; align-items: center; justify-content: space-between; gap: 14px;
  padding: 18px 20px;
  background: var(--surface-card);
  border: 1px solid var(--border-color);
  border-radius: 14px;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
}
.session-card:hover {
  border-color: var(--brand-200);
  box-shadow: 0 6px 20px rgba(37, 99, 235, 0.07);
  transform: translateY(-1px);
}

.session-card__body { flex: 1; min-width: 0; }

.session-card__title {
  margin: 0 0 6px;
  font-size: 15px; font-weight: 700; color: var(--text-1);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

.session-card__meta {
  display: flex; align-items: center; flex-wrap: wrap; gap: 6px;
  font-size: 12.5px; color: var(--text-4);
}
.session-card__sep { color: var(--text-5); }

.session-card__actions {
  display: flex; gap: 4px; flex-shrink: 0;
}

.session-card__btn {
  display: flex; align-items: center; justify-content: center;
  width: 32px; height: 32px; border: none; border-radius: 8px;
  background: transparent; color: var(--text-4);
  cursor: pointer; transition: all 0.15s ease;
}
.session-card__btn:hover {
  background: var(--surface-hover); color: var(--brand-600);
}
.session-card__btn--danger:hover {
  background: rgba(220, 38, 38, 0.08); color: #dc2626;
}

.turn-preview-list {
  display: flex; flex-direction: column; gap: 10px;
}

.turn-item {
  padding: 14px 16px; border-radius: 12px;
  background: var(--surface-muted); border: 1px solid var(--border-color);
}
.turn-item__label {
  font-size: 11.5px; font-weight: 700; color: var(--brand-600);
  margin-bottom: 6px;
}
.turn-item__text {
  font-size: 14px; line-height: 1.7; color: var(--text-2);
}
.turn-item__text--answer {
  color: var(--text-3);
  font-size: 13.5px;
}
.turn-item__footer {
  display: flex; gap: 14px; margin-top: 10px; padding-top: 10px;
  border-top: 1px solid var(--border-color);
  font-size: 12px; color: var(--text-4);
}

@media (max-width: 900px) {
  .sessions-overview-grid { grid-template-columns: 1fr; }
  .session-card-grid { grid-template-columns: 1fr; }
}
</style>