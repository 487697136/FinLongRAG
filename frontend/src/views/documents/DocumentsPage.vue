<template>
  <div class="documents-page page-shell">
    <PageHeader title="文档资产" description="集中管理金融资料上传、处理状态与失败恢复，确保知识库中的证据始终可追溯、可检索。">
      <template #actions>
        <n-space>
          <input ref="fileInputRef" type="file" class="visually-hidden" accept=".txt,.md,.json,.csv,.pdf,.xlsx,.html,.htm" multiple @change="handleFileSelected" />
          <n-button type="primary" :loading="uploading" @click="handleUploadDocument">
            {{ uploading ? '上传中...' : '上传文档' }}
          </n-button>
        </n-space>
      </template>
    </PageHeader>

    <div v-if="uploading" class="upload-progress-panel">
      <div class="upload-progress-panel__meta">
        <strong>{{ uploadProgressLabel }}</strong>
        <span>{{ uploadProgress.percentage }}%</span>
      </div>
      <n-progress
        :percentage="uploadProgress.percentage"
        :height="6"
        :border-radius="3"
        :show-indicator="false"
        status="info"
      />
    </div>

    <div class="documents-overview-grid">
      <InfoCard label="已完成" :value="completedCount" caption="已完成解析并可作为问答证据使用的文档" tone="info" />
      <InfoCard label="处理中" :value="processingCount" caption="系统自动轮询更新文档处理进度" tone="info" />
      <InfoCard label="失败任务" :value="failedCount" caption="支持重试并重新构建对应知识库索引" tone="info" />
    </div>

    <FilterToolbar :tabs="documentTabs" :active-tab="activeDocumentTab" @update:active-tab="activeDocumentTab = $event">
      <template #filters>
        <n-input v-model:value="searchKeyword" clearable placeholder="搜索文档名称或资料主题" style="min-width: 260px; flex: 1" />
        <n-select v-model:value="selectedKnowledgeBaseId" :options="knowledgeBaseFilterOptions" style="width: 220px" />
        <n-select v-model:value="selectedStatus" :options="statusOptions" style="width: 160px" />
      </template>
      <template #summary>
        <div class="toolbar-summary">
          <span>当前列表 {{ filteredDocumentList.length }} 条</span>
          <span v-if="selectedKnowledgeBaseName">知识库：{{ selectedKnowledgeBaseName }}</span>
          <span v-if="processingCount > 0" class="toolbar-summary__polling">
            <n-spin :size="12" style="display:inline-flex" /> 自动轮询更新中
          </span>
        </div>
      </template>
    </FilterToolbar>

    <SectionCard title="文档任务列表" description="查看解析状态、证据切块产出与失败恢复情况。" flush>
      <n-spin :show="loading">
        <n-data-table :columns="documentTableColumns" :data="filteredDocumentList" :pagination="{ pageSize: 8 }" :row-key="(row) => row.id" />
        <AppEmpty v-if="!filteredDocumentList.length" description="当前筛选条件下没有文档" />
      </n-spin>
    </SectionCard>

    <!-- 文档详情抽屉 -->
    <n-drawer v-model:show="showDocumentDrawer" placement="right" :width="640">
      <n-drawer-content title="文档详情" closable body-content-style="padding: 16px">
        <DetailPanel v-if="selectedDocumentRecord" :title="selectedDocumentRecord.name" description="查看文档状态、错误原因与切块统计。">
          <template #actions>
            <n-space>
              <n-button v-if="selectedDocumentRecord.status === 'failed'" type="primary" secondary @click="handleReprocessDocument(selectedDocumentRecord.id)">重试</n-button>
              <n-button type="error" quaternary @click="confirmDeleteDocument(selectedDocumentRecord)">删除文档</n-button>
            </n-space>
          </template>
          <div class="detail-meta-list">
            <div class="detail-meta-item"><span>文档 ID</span><strong>{{ selectedDocumentRecord.id }}</strong></div>
            <div class="detail-meta-item"><span>所属知识库</span><strong>{{ selectedDocumentRecord.kbName }}</strong></div>
            <div class="detail-meta-item"><span>文件类型</span><strong>{{ selectedDocumentRecord.file_type || '--' }}</strong></div>
            <div class="detail-meta-item"><span>文件大小</span><strong>{{ formatBytes(selectedDocumentRecord.file_size) }}</strong></div>
            <div class="detail-meta-item"><span>处理状态</span><strong>{{ formatDocumentStatus(selectedDocumentRecord.status) }}</strong></div>
            <div class="detail-meta-item"><span>切块数量</span><strong>{{ selectedDocumentRecord.chunk_count || 0 }}</strong></div>
            <div class="detail-meta-item"><span>上传耗时</span><strong>{{ formatDuration(selectedDocumentRecord.upload_duration_ms) }}</strong></div>
            <div class="detail-meta-item"><span>处理耗时</span><strong>{{ formatDuration(selectedDocumentRecord.processing_duration_ms) }}</strong></div>
            <div class="detail-meta-item detail-meta-item--full"><span>错误信息</span><strong>{{ selectedDocumentRecord.error_message || '无' }}</strong></div>
            <div class="detail-meta-item"><span>创建时间</span><strong>{{ formatDateTime(selectedDocumentRecord.created_at) }}</strong></div>
            <div class="detail-meta-item"><span>更新时间</span><strong>{{ formatDateTime(selectedDocumentRecord.updated_at) }}</strong></div>
            <div class="detail-meta-item"><span>完成时间</span><strong>{{ formatDateTime(selectedDocumentRecord.processed_at) }}</strong></div>
          </div>
        </DetailPanel>
      </n-drawer-content>
    </n-drawer>

    <!-- 删除确认弹窗 -->
    <n-modal
      v-model:show="showDeleteConfirm"
      preset="dialog"
      type="error"
      title="删除文档"
      positive-text="确认删除"
      negative-text="取消"
      :loading="deleting"
      @positive-click="handleDeleteDocument"
      @negative-click="showDeleteConfirm = false"
    >
      <template #default>
        <p>确定要删除文档 <strong>「{{ pendingDeleteDoc?.name }}」</strong> 吗？</p>
        <template v-if="pendingDeleteDoc?.status === 'completed' && deleteKbRemainingCount > 0">
          <div class="delete-warn-box">
            <div class="delete-warn-box__icon">⚠️</div>
            <div>
              <div class="delete-warn-box__title">将触发知识库全量重建</div>
              <div class="delete-warn-box__desc">
                该文档已成功入库，删除后系统需要对知识库内剩余 <strong>{{ deleteKbRemainingCount }}</strong> 个文档重新进行向量化和索引构建，耗时可能较长。
              </div>
            </div>
          </div>
        </template>
        <p v-else style="color: var(--text-4); font-size: 13px; margin-top: 8px">
          {{ pendingDeleteDoc?.status !== 'completed' ? '该文档尚未成功入库，删除后不会触发知识库重建。' : '知识库中无其他文档，将直接清理运行时数据。' }}
        </p>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { NButton, NDataTable, NDrawer, NDrawerContent, NModal, NProgress, NSpace, NInput, NSelect, NSpin, useMessage } from 'naive-ui'
import { EyeOutline, RefreshOutline, TrashOutline } from '@vicons/ionicons5'
import { deleteDocument, getDocumentProgress, listDocumentsByKnowledgeBase, reprocessDocument, uploadDocument, uploadDocumentsBatch } from '@/api/api'
import AppEmpty from '@/components/common/AppEmpty.vue'
import DetailPanel from '@/components/common/DetailPanel.vue'
import FilterToolbar from '@/components/common/FilterToolbar.vue'
import InfoCard from '@/components/common/InfoCard.vue'
import SectionCard from '@/components/common/SectionCard.vue'
import PageHeader from '@/components/layout/PageHeader.vue'
import { formatBytes, formatDateTime, formatDocumentStatus, statusToneFromDocument } from '@/utils/formatters'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBase'

const route = useRoute()
const message = useMessage()
const kbStore = useKnowledgeBaseStore()

const loading = ref(false)
const uploading = ref(false)
const deleting = ref(false)
const fileInputRef = ref(null)
const uploadProgress = ref({ loaded: 0, total: 0, percentage: 0, fileCount: 0 })
const documentRecordList = ref([])
const searchKeyword = ref('')
const selectedKnowledgeBaseId = ref(route.query.kb ? String(route.query.kb) : 'all')
const selectedStatus = ref('all')
const activeDocumentTab = ref('all')
const showDocumentDrawer = ref(false)
const showDeleteConfirm = ref(false)
const pendingDeleteDoc = ref(null)
const selectedDocumentId = ref('')
let pollTimer = null
let progressPollTimer = null

const knowledgeBaseFilterOptions = computed(() => [
  { label: '全部知识库', value: 'all' },
  ...kbStore.list.map((item) => ({ label: item.name, value: String(item.id) }))
])

const statusOptions = [
  { label: '全部状态', value: 'all' },
  { label: '已完成', value: 'completed' },
  { label: '处理中', value: 'processing' },
  { label: '待处理', value: 'pending' },
  { label: '失败', value: 'failed' }
]

const completedCount = computed(() => documentRecordList.value.filter((item) => item.status === 'completed').length)
const processingCount = computed(() => documentRecordList.value.filter((item) => ['processing', 'pending'].includes(item.status)).length)
const failedCount = computed(() => documentRecordList.value.filter((item) => item.status === 'failed').length)
const selectedKnowledgeBaseName = computed(() => kbStore.list.find((item) => String(item.id) === selectedKnowledgeBaseId.value)?.name || '')
const uploadProgressLabel = computed(() => {
  const count = uploadProgress.value.fileCount || 1
  return count > 1 ? `正在上传 ${count} 个文档` : '正在上传文档'
})

const documentTabs = computed(() => [
  { label: '全部', value: 'all', count: documentRecordList.value.length },
  { label: '已完成', value: 'completed', count: completedCount.value },
  { label: '处理中', value: 'processing', count: processingCount.value },
  { label: '失败', value: 'failed', count: failedCount.value }
])

const filteredDocumentList = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase()
  return documentRecordList.value.filter((item) => {
    if (selectedKnowledgeBaseId.value !== 'all' && String(item.knowledge_base_id) !== selectedKnowledgeBaseId.value) return false
    if (selectedStatus.value !== 'all' && item.status !== selectedStatus.value) return false
    if (activeDocumentTab.value !== 'all' && !(activeDocumentTab.value === 'processing' ? ['processing', 'pending'].includes(item.status) : item.status === activeDocumentTab.value)) return false
    if (!keyword) return true
    return String(item.name || '').toLowerCase().includes(keyword)
  })
})

const selectedDocumentRecord = computed(() => documentRecordList.value.find((item) => String(item.id) === selectedDocumentId.value) || null)

// 当前待删文档所在知识库的其他已完成文档数量（用于确认弹窗提示重建影响）
const deleteKbRemainingCount = computed(() => {
  if (!pendingDeleteDoc.value) return 0
  return documentRecordList.value.filter(
    (item) =>
      String(item.knowledge_base_id) === String(pendingDeleteDoc.value.knowledge_base_id) &&
      item.id !== pendingDeleteDoc.value.id &&
      item.status === 'completed'
  ).length
})

async function loadDocuments() {
  loading.value = true
  try {
    const knowledgeBases = await kbStore.fetchList()
    const groups = await Promise.all(knowledgeBases.map(async (kb) => {
      const docs = await listDocumentsByKnowledgeBase(kb.id)
      return docs.map((doc) => ({ ...doc, kbName: kb.name }))
    }))
    documentRecordList.value = groups.flat().sort((a, b) => new Date(b.updated_at || b.created_at) - new Date(a.updated_at || a.created_at))
  } catch (error) {
    message.error(error.response?.data?.detail || '加载文档列表失败')
  } finally {
    loading.value = false
  }
}

async function pollProcessingProgress() {
  const processingDocs = documentRecordList.value.filter((item) =>
    ['processing', 'pending'].includes(item.status)
  )
  if (!processingDocs.length) return
  await Promise.allSettled(
    processingDocs.map(async (doc) => {
      try {
        const prog = await getDocumentProgress(doc.id)
        const target = documentRecordList.value.find((d) => d.id === doc.id)
        if (!target) return
        target.progress = prog.progress ?? 0
        target.progress_stage = prog.progress_stage ?? ''
        target.processing_duration_ms = prog.processing_duration_ms ?? target.processing_duration_ms
        target.stage_timings = prog.stage_timings ?? target.stage_timings
        target.last_ingestion_task_id = prog.last_ingestion_task_id ?? target.last_ingestion_task_id
        if (prog.status !== target.status) {
          target.status = prog.status
          target.error_message = prog.error_message
          if (['completed', 'failed'].includes(prog.status)) {
            // 状态终止时触发一次完整刷新以获取 chunk_count 等字段
            await loadDocuments()
          }
        }
      } catch (_e) {
        // 静默忽略单个文档进度查询失败
      }
    })
  )
}

function ensurePolling() {
  if (pollTimer) clearInterval(pollTimer)
  if (progressPollTimer) clearInterval(progressPollTimer)
  const hasProcessing = documentRecordList.value.some((item) =>
    ['processing', 'pending'].includes(item.status)
  )
  if (!hasProcessing) return
  // 每 2 秒快速轮询进度（轻量端点），页面隐藏时暂停
  progressPollTimer = window.setInterval(() => {
    if (document.hidden) return
    pollProcessingProgress()
  }, 2000)
  // 每 10 秒做一次全量刷新，页面隐藏时暂停
  pollTimer = window.setInterval(() => {
    if (document.hidden) return
    loadDocuments()
  }, 10000)
}

function handleUploadDocument() {
  if (selectedKnowledgeBaseId.value === 'all') {
    message.warning('请先选择一个知识库再上传文档')
    return
  }
  fileInputRef.value?.click()
}

async function handleFileSelected(event) {
  const files = Array.from(event.target.files || [])
  if (!files.length) return
  uploading.value = true
  uploadProgress.value = {
    loaded: 0,
    total: files.reduce((sum, file) => sum + (file.size || 0), 0),
    percentage: 0,
    fileCount: files.length
  }
  const onUploadProgress = (progressEvent) => {
    const total = progressEvent.total || uploadProgress.value.total || 0
    const loaded = progressEvent.loaded || 0
    uploadProgress.value = {
      ...uploadProgress.value,
      loaded,
      total,
      percentage: total > 0 ? Math.min(99, Math.round((loaded / total) * 100)) : uploadProgress.value.percentage
    }
  }
  const loadingMsg = message.loading(files.length > 1 ? `正在上传 ${files.length} 个文档...` : `正在上传「${files[0].name}」...`, { duration: 0 })
  try {
    if (files.length > 1) {
      await uploadDocumentsBatch(selectedKnowledgeBaseId.value, files, { onUploadProgress })
    } else {
      await uploadDocument(selectedKnowledgeBaseId.value, files[0], { onUploadProgress })
    }
    uploadProgress.value = { ...uploadProgress.value, percentage: 100 }
    loadingMsg.destroy()
    message.success(files.length > 1 ? '文档批量提交成功，系统正在统一处理' : '文档已提交，系统正在处理（页面将自动刷新状态）')
    kbStore.invalidate()
    await loadDocuments()
  } catch (error) {
    loadingMsg.destroy()
    message.error(error.response?.data?.detail || '上传文档失败')
  } finally {
    uploading.value = false
    uploadProgress.value = { loaded: 0, total: 0, percentage: 0, fileCount: 0 }
    event.target.value = ''
  }
}

function openDocumentDetail(documentId) {
  selectedDocumentId.value = String(documentId)
  showDocumentDrawer.value = true
}

async function handleReprocessDocument(documentId) {
  try {
    await reprocessDocument(documentId)
    message.success('已提交重试任务，知识库运行时将重新构建')
    await loadDocuments()
  } catch (error) {
    message.error(error.response?.data?.detail || '重试文档失败')
  }
}

function confirmDeleteDocument(doc) {
  pendingDeleteDoc.value = doc
  showDeleteConfirm.value = true
}

function formatDuration(value) {
  const ms = Number(value || 0)
  if (!ms) return '--'
  if (ms < 1000) return `${ms}ms`
  const seconds = Math.round(ms / 1000)
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return rest ? `${minutes}m ${rest}s` : `${minutes}m`
}

async function handleDeleteDocument() {
  if (!pendingDeleteDoc.value) return
  deleting.value = true
  try {
    await deleteDocument(pendingDeleteDoc.value.id)
    if (selectedDocumentId.value === String(pendingDeleteDoc.value.id)) showDocumentDrawer.value = false
    showDeleteConfirm.value = false
    message.success('文档已删除，运行时数据已同步处理')
    kbStore.invalidate()
    await loadDocuments()
  } catch (error) {
    message.error(error.response?.data?.detail || '删除文档失败')
  } finally {
    deleting.value = false
    pendingDeleteDoc.value = null
  }
}

const documentTableColumns = computed(() => [
  { title: '文档名称', key: 'name', minWidth: 240, ellipsis: { tooltip: true } },
  { title: '知识库', key: 'kbName', minWidth: 120 },
  { title: '类型', key: 'file_type', width: 80 },
  { title: '大小', key: 'file_size', width: 100, render: (row) => formatBytes(row.file_size) },
  {
    title: '状态 / 进度', key: 'status', minWidth: 180,
    render: (row) => {
      const isProcessing = ['processing', 'pending'].includes(row.status)
      const badge = h('span', {
        class: ['status-badge', `status-badge--${statusToneFromDocument(row.status)}`]
      }, formatDocumentStatus(row.status))
      if (!isProcessing) return badge
      const pct = row.progress ?? 0
      const stage = row.progress_stage || '处理中...'
      return h('div', { class: 'progress-cell' }, [
        h('div', { class: 'progress-cell__header' }, [
          badge,
          h('span', { class: 'progress-cell__pct' }, `${pct}%`)
        ]),
        h(NProgress, {
          percentage: pct,
          height: 4,
          borderRadius: 2,
          indicatorPlacement: 'inside',
          showIndicator: false,
          status: pct === 100 ? 'success' : 'default',
          style: 'margin-top:4px'
        }),
        h('span', { class: 'progress-cell__stage' }, stage)
      ])
    }
  },
  { title: '切块', key: 'chunk_count', width: 72 },
  { title: '更新时间', key: 'updated_at', width: 150, render: (row) => formatDateTime(row.updated_at) },
  {
    title: '操作', key: 'actions', width: 140,
    render: (row) => h(NSpace, { size: 6 }, { default: () => [
      h(NButton, { text: true, onClick: () => openDocumentDetail(row.id) }, { icon: () => h(EyeOutline) }),
      row.status === 'failed' ? h(NButton, { text: true, type: 'primary', onClick: () => handleReprocessDocument(row.id) }, { icon: () => h(RefreshOutline) }) : null,
      h(NButton, { text: true, type: 'error', onClick: () => confirmDeleteDocument(row) }, { icon: () => h(TrashOutline) })
    ].filter(Boolean) })
  }
])

watch(documentRecordList, ensurePolling, { deep: true })
onMounted(loadDocuments)
onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (progressPollTimer) clearInterval(progressPollTimer)
})
</script>

<style scoped>
.documents-overview-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; }
.upload-progress-panel { margin-bottom:16px; padding:12px 14px; border:1px solid var(--border-color); border-radius:8px; background:var(--surface-card); }
.upload-progress-panel__meta { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:8px; color:var(--text-2); font-size:13px; }
.upload-progress-panel__meta strong { color:var(--text-1); font-size:14px; }
.toolbar-summary { display:flex; flex-wrap:wrap; gap:16px; color:var(--text-4); font-size:13px; align-items:center; }
.toolbar-summary__polling { display:inline-flex; align-items:center; gap:6px; color:var(--brand-600); font-size:12px; }
.detail-meta-list { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }
.detail-meta-item { padding:14px 16px; border-radius:12px; background:var(--surface-muted); border:1px solid var(--border-color); display:flex; flex-direction:column; gap:6px; }
.detail-meta-item span { font-size:12px; color:var(--text-4); }
.detail-meta-item strong { font-size:14px; color:var(--text-1); word-break:break-word; }
.detail-meta-item--full { grid-column:1 / -1; }
.visually-hidden { position:absolute; width:1px; height:1px; opacity:0; pointer-events:none; }
@media (max-width: 1100px) { .documents-overview-grid,.detail-meta-list { grid-template-columns:1fr; } }

.delete-warn-box {
  display: flex;
  gap: 10px;
  margin-top: 12px;
  padding: 12px 14px;
  background: var(--status-warning-bg);
  border: 1px solid var(--warning-color);
  border-radius: 10px;
}
.delete-warn-box__icon { font-size: 16px; flex-shrink: 0; margin-top: 1px; }
.delete-warn-box__title { font-size: 13px; font-weight: 700; color: var(--status-warning-text); margin-bottom: 4px; }
.delete-warn-box__desc { font-size: 12px; color: var(--status-warning-text); line-height: 1.6; }

.progress-cell { display: flex; flex-direction: column; gap: 2px; min-width: 160px; }
.progress-cell__header { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.progress-cell__pct { font-size: 11px; font-weight: 600; color: var(--brand-600); white-space: nowrap; }
.progress-cell__stage { font-size: 11px; color: var(--text-4); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
</style>
