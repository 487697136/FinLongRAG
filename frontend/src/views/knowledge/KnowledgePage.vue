<template>
  <div class="knowledge-page page-shell">
    <PageHeader
      title="知识库"
      description="沉淀财报、研报、公告与制度资料，构建可问答、可追溯的金融知识资产。"
    >
      <template #actions>
        <n-button type="primary" @click="showCreateModal = true">新建知识库</n-button>
      </template>
    </PageHeader>
    <!-- 重建确认弹窗 -->
    <n-modal
      v-model:show="showRebuildConfirm"
      preset="dialog"
      type="warning"
      title="完整重建知识库"
      positive-text="确认执行"
      negative-text="取消"
      :loading="rebuilding"
      @positive-click="executeRebuild"
      @negative-click="showRebuildConfirm = false"
    >
      <template #default>
        <div class="rebuild-confirm-body">
          <p>将清空整个工作目录，重新运行文档切块、向量化和索引构建，耗时较长（通常数十分钟）。</p>
          <div class="rebuild-confirm-meta">
            <n-icon size="15" color="var(--warning-color)" style="margin-right:4px">
              <svg viewBox="0 0 24 24"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/></svg>
            </n-icon>
            <span>此操作将清空工作目录并重新处理所有文档，耗时较长。</span>
          </div>
        </div>
      </template>
    </n-modal>

    <div class="knowledge-overview-grid">
      <InfoCard label="知识库总数" :value="kbStore.list.length" caption="当前账号下全部金融研究知识库" tone="info" />
      <InfoCard label="已就绪" :value="kbStore.readyCount" caption="已完成初始化，可直接进入问答分析的知识库" tone="info" />
      <InfoCard label="文档总量" :value="kbStore.documentTotal" caption="累计纳入知识库的金融文档数量" tone="info" />
      <InfoCard label="切块总量" :value="kbStore.chunkTotal" caption="沉淀为可检索证据片段的文本总量" tone="info" />
    </div>

    <FilterToolbar :tabs="statusTabs" :active-tab="selectedStatus" @update:active-tab="selectedStatus = $event">
      <template #filters>
        <n-input v-model:value="searchKeyword" clearable placeholder="按名称、用途或资料范围搜索知识库" style="min-width: 280px; flex: 1" />
      </template>
    </FilterToolbar>

    <n-spin :show="kbStore.loading && !kbStore.list.length">
      <div class="knowledge-grid">
        <SectionCard v-for="kb in filteredKnowledgeBaseList" :key="kb.id" :title="kb.name" :description="kb.description || '暂无描述'" size="compact">
          <template #extra>
            <span :class="['status-badge', `status-badge--${statusToneFromKnowledgeBase(kb)}`]">{{ statusLabelFromKnowledgeBase(kb) }}</span>
          </template>
          <div class="knowledge-card">
            <div class="knowledge-card__metrics">
              <div class="knowledge-metric"><span>文档</span><strong>{{ kb.document_count }}</strong></div>
              <div class="knowledge-metric"><span>切块</span><strong>{{ kb.total_chunks }}</strong></div>
              <div class="knowledge-metric"><span>状态</span><strong>{{ kb.is_initialized ? '已就绪' : '待处理' }}</strong></div>
            </div>
            <div class="knowledge-card__footer">
              <div class="knowledge-card__updated">更新于 {{ formatDateTime(kb.updated_at) }}</div>
              <n-space>
                <n-button size="small" @click="handleOpenDocuments(kb)">文档</n-button>
                <n-button size="small" @click="openDetailDrawer(kb)">详情</n-button>
              </n-space>
            </div>
          </div>
        </SectionCard>
      </div>
    </n-spin>

    <AppEmpty v-if="!kbStore.loading && !filteredKnowledgeBaseList.length" description="当前筛选条件下没有匹配的知识库。" />

    <!-- 详情抽屉 -->
    <n-drawer v-model:show="showDetailDrawer" placement="right" :width="620">
      <n-drawer-content title="知识库详情" closable body-content-style="padding: 16px">
        <DetailPanel v-if="selectedKnowledgeBase" :title="selectedKnowledgeBase.name" :description="selectedKnowledgeBase.description || '暂无描述'" :tabs="detailTabs" :active-tab="activeDetailTab" @update:active-tab="activeDetailTab = $event">
          <template #actions>
            <n-space>
              <n-button
                type="primary"
                secondary
                :loading="rebuilding"
                :disabled="rebuilding || cleaning"
                @click="confirmRebuild"
                style="min-width: 72px"
              >
                {{ rebuilding ? '重建中...' : '重建索引' }}
              </n-button>
              <n-button
                secondary
                :loading="cleaning"
                :disabled="rebuilding || cleaning"
                @click="handleCleanupKnowledgeBase(selectedKnowledgeBase.id)"
              >
                {{ cleaning ? '清理中...' : '清理运行时' }}
              </n-button>
              <n-button type="error" quaternary :disabled="rebuilding || cleaning" @click="confirmDeleteKnowledgeBase(selectedKnowledgeBase)">删除</n-button>
            </n-space>
          </template>

          <template v-if="activeDetailTab === 'basic'">
            <div class="detail-meta-list">
              <div class="detail-meta-item"><span>ID</span><strong>{{ selectedKnowledgeBase.id }}</strong></div>
              <div class="detail-meta-item"><span>初始化状态</span><strong>{{ selectedKnowledgeBase.is_initialized ? '已完成' : '未完成' }}</strong></div>
              <div class="detail-meta-item"><span>创建时间</span><strong>{{ formatDateTime(selectedKnowledgeBase.created_at) }}</strong></div>
              <div class="detail-meta-item"><span>更新时间</span><strong>{{ formatDateTime(selectedKnowledgeBase.updated_at) }}</strong></div>
            </div>
          </template>

          <template v-else-if="activeDetailTab === 'stats'">
            <n-spin :show="detailStatsLoading">
              <div v-if="selectedKnowledgeBaseStats" class="detail-meta-list">
                <div class="detail-meta-item"><span>后端状态</span><strong>{{ statusLabel }}</strong></div>
                <div class="detail-meta-item"><span>文档数量</span><strong>{{ selectedKnowledgeBaseStats.document_count || 0 }}</strong></div>
                <div class="detail-meta-item"><span>切块数量</span><strong>{{ selectedKnowledgeBaseStats.chunks || 0 }}</strong></div>
                <div class="detail-meta-item detail-meta-item--full"><span>最近错误</span><strong>{{ selectedKnowledgeBaseStats.last_error || '无' }}</strong></div>
              </div>
            </n-spin>
          </template>
        </DetailPanel>
      </n-drawer-content>
    </n-drawer>

    <!-- 新建知识库弹窗 -->
    <n-modal v-model:show="showCreateModal" preset="card" style="max-width: 480px" title="新建知识库">
      <div class="create-form">
        <n-form-item label="名称"><n-input v-model:value="createForm.name" placeholder="输入知识库名称" /></n-form-item>
        <n-form-item label="描述（可选）"><n-input v-model:value="createForm.description" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" placeholder="简要说明知识库的用途或资料范围" /></n-form-item>
      </div>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showCreateModal = false">取消</n-button>
          <n-button type="primary" :loading="creating" @click="handleCreateKnowledgeBase">创建</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 删除确认弹窗 -->
    <n-modal v-model:show="showDeleteConfirm" preset="dialog" type="error" title="删除知识库" positive-text="确认删除" negative-text="取消" :loading="deleting" @positive-click="handleDeleteKnowledgeBase" @negative-click="showDeleteConfirm = false">
      <template #default>
        <p>确定要删除知识库 <strong>「{{ pendingDeleteKb?.name }}」</strong> 吗？</p>
        <p style="color: var(--text-4); font-size: 13px; margin-top: 8px">此操作不可恢复，所有相关文档和检索索引数据将被永久清除。</p>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NDrawer, NDrawerContent, NFormItem, NIcon, NInput, NModal, NSpace, NSpin, NSwitch, useMessage } from 'naive-ui'
import { cleanupKnowledgeBase, createKnowledgeBase, deleteKnowledgeBase, rebuildKnowledgeBase } from '@/api/api'
import AppEmpty from '@/components/common/AppEmpty.vue'
import DetailPanel from '@/components/common/DetailPanel.vue'
import FilterToolbar from '@/components/common/FilterToolbar.vue'
import InfoCard from '@/components/common/InfoCard.vue'
import SectionCard from '@/components/common/SectionCard.vue'
import PageHeader from '@/components/layout/PageHeader.vue'
import { formatDateTime, statusLabelFromKnowledgeBase, statusToneFromKnowledgeBase } from '@/utils/formatters'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBase'

const router = useRouter()
const message = useMessage()
const kbStore = useKnowledgeBaseStore()

const creating = ref(false)
const rebuilding = ref(false)
const cleaning = ref(false)
const deleting = ref(false)

// 重建模式相关状态
const showRebuildConfirm = ref(false)
const pendingRebuildMode = ref('full')   // 'full' | 'graph' | 'vectors'
const rebuildingLabel = ref('重建中...')

const rebuildConfirmTitle = computed(() => '完整重建知识库')

const rebuildConfirmDesc = computed(() => '将清空整个工作目录，重新运行文档切块、实体抽取和向量索引，耗时较长（通常数十分钟）。')
const searchKeyword = ref('')
const selectedStatus = ref('all')
const showDetailDrawer = ref(false)
const showCreateModal = ref(false)
const showDeleteConfirm = ref(false)
const pendingDeleteKb = ref(null)
const selectedKnowledgeBaseId = ref('')
const activeDetailTab = ref('basic')
const detailStatsLoading = ref(false)
const selectedKnowledgeBaseStats = ref(null)

const createForm = reactive({ name: '', description: '' })
const detailTabs = [{ label: '基本信息', value: 'basic' }, { label: '运行状态', value: 'stats' }]

const statusTabs = computed(() => [
  { label: '全部', value: 'all', count: kbStore.list.length },
  { label: '已就绪', value: 'initialized', count: kbStore.readyCount },
  { label: '构建中', value: 'building', count: kbStore.list.filter((item) => !item.is_initialized && item.document_count > 0).length },
  { label: '空知识库', value: 'empty', count: kbStore.list.filter((item) => item.document_count === 0).length }
])

const filteredKnowledgeBaseList = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase()
  return kbStore.list.filter((item) => {
    if (selectedStatus.value === 'initialized' && !item.is_initialized) return false
    if (selectedStatus.value === 'building' && (item.is_initialized || item.document_count === 0)) return false
    if (selectedStatus.value === 'empty' && item.document_count > 0) return false
    if (!keyword) return true
    return [item.name, item.description].join(' ').toLowerCase().includes(keyword)
  })
})

const selectedKnowledgeBase = computed(() => kbStore.list.find((item) => String(item.id) === String(selectedKnowledgeBaseId.value)) || null)
const statusLabel = computed(() => ({ ready: '就绪', error: '异常' }[selectedKnowledgeBaseStats.value?.status] || '未知'))

async function loadKnowledgeBaseStats(kbId) {
  if (!kbId) return
  detailStatsLoading.value = true
  try {
    selectedKnowledgeBaseStats.value = await kbStore.fetchStats(kbId, true)
  } finally {
    detailStatsLoading.value = false
  }
}

function resetCreateForm() {
  createForm.name = ''
  createForm.description = ''
}

async function handleCreateKnowledgeBase() {
  if (!createForm.name.trim()) {
    message.warning('请输入知识库名称')
    return
  }
  creating.value = true
  try {
    await createKnowledgeBase({ ...createForm, name: createForm.name.trim() })
    showCreateModal.value = false
    resetCreateForm()
    message.success('知识库已创建')
    await kbStore.fetchList(true)
  } catch (error) {
    message.error(error.response?.data?.detail || '创建知识库失败')
  } finally {
    creating.value = false
  }
}

function handleOpenDocuments(kb) { router.push({ name: 'Documents', query: { kb: kb.id } }) }

async function openDetailDrawer(kb) {
  selectedKnowledgeBaseId.value = String(kb.id)
  activeDetailTab.value = 'basic'
  selectedKnowledgeBaseStats.value = null
  showDetailDrawer.value = true
  await loadKnowledgeBaseStats(kb.id)
}

function confirmRebuild() {
  pendingRebuildMode.value = 'full'
  showRebuildConfirm.value = true
}

async function executeRebuild() {
  if (!selectedKnowledgeBase.value) return
  const kbId = selectedKnowledgeBase.value.id
  const mode = pendingRebuildMode.value
  showRebuildConfirm.value = false
  rebuilding.value = true

  try {
    await rebuildKnowledgeBase(kbId)
    message.success('知识库完整重建完成')
    kbStore.invalidate(kbId)
    await Promise.all([kbStore.fetchList(true), loadKnowledgeBaseStats(kbId)])
  } catch (error) {
    message.error(error.response?.data?.detail || '完整重建失败')
  } finally {
    rebuilding.value = false
  }
}

async function handleCleanupKnowledgeBase(kbId) {
  cleaning.value = true
  try {
    await cleanupKnowledgeBase(kbId)
    message.success('运行时数据已清理')
    kbStore.invalidate(kbId)
    await Promise.all([kbStore.fetchList(true), loadKnowledgeBaseStats(kbId)])
  } catch (error) {
    message.error(error.response?.data?.detail || '清理知识库运行时失败')
  } finally {
    cleaning.value = false
  }
}

function confirmDeleteKnowledgeBase(kb) {
  pendingDeleteKb.value = kb
  showDeleteConfirm.value = true
}

async function handleDeleteKnowledgeBase() {
  if (!pendingDeleteKb.value) return
  deleting.value = true
  try {
    await deleteKnowledgeBase(pendingDeleteKb.value.id)
    showDeleteConfirm.value = false
    showDetailDrawer.value = false
    message.success('知识库已删除')
    kbStore.invalidate()
    await kbStore.fetchList(true)
  } catch (error) {
    message.error(error.response?.data?.detail || '删除知识库失败')
  } finally {
    deleting.value = false
    pendingDeleteKb.value = null
  }
}

onMounted(() => kbStore.fetchList())
</script>

<style scoped>
.knowledge-overview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.knowledge-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.knowledge-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.knowledge-card__metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.knowledge-metric {
  padding: 12px 14px;
  border-radius: 10px;
  background: linear-gradient(180deg, var(--surface-muted) 0%, var(--surface-soft) 100%);
  border: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  gap: 4px;
  transition: border-color 0.16s;
}

.knowledge-metric:hover {
  border-color: var(--brand-soft-border);
}

.knowledge-metric span {
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  color: var(--text-5);
}

.knowledge-metric strong {
  font-size: 20px;
  font-weight: 800;
  color: var(--text-1);
  letter-spacing: -0.5px;
}

.knowledge-card__footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--border-color);
}

.knowledge-card__updated {
  font-size: 12px;
  color: var(--text-5);
}

.create-form__switches,
.detail-meta-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.detail-meta-item {
  padding: 14px 16px;
  border-radius: 12px;
  background: var(--surface-muted);
  border: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.detail-meta-item span {
  font-size: 12px;
  color: var(--text-4);
}

.detail-meta-item strong {
  font-size: 14px;
  color: var(--text-1);
  word-break: break-word;
}

.detail-meta-item--full {
  grid-column: 1 / -1;
}

.rebuild-confirm-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.rebuild-confirm-body p {
  margin: 0;
  font-size: 14px;
  color: var(--text-2);
  line-height: 1.6;
}

.rebuild-confirm-meta {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--surface-muted);
  border: 1px solid var(--border-color);
  font-size: 13px;
  color: var(--text-3);
  line-height: 1.5;
}

@media (max-width: 1200px) {
  .knowledge-overview-grid,
  .knowledge-grid,
  .create-form__switches,
  .detail-meta-list,
  .knowledge-card__metrics {
    grid-template-columns: 1fr;
  }
}
</style>
