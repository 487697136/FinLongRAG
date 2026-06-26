<template>
  <n-layout class="page">
    <n-layout-header class="page__header">
      <div class="header-left">
        <n-button size="small" tertiary @click="router.push('/evaluations')">
          <template #icon>
            <n-icon :component="ArrowBackOutline" />
          </template>
          返回
        </n-button>
        <div>
          <h2>评测报告</h2>
          <p v-if="report">{{ report.kb_name }} / {{ report.test_set_name }}</p>
        </div>
      </div>
      <n-space>
        <n-select
          v-if="compareOptions.length"
          v-model:value="compareId"
          :options="compareOptions"
          placeholder="选择历史报告对比"
          clearable
          style="width: 240px"
        />
        <n-button tertiary @click="loadReport">刷新</n-button>
      </n-space>
    </n-layout-header>

    <n-layout-content class="page__content">
      <n-spin :show="loading">
        <n-empty v-if="!loading && !report" description="评测报告不存在" />

        <template v-if="report">
          <n-card class="section" size="small" title="基础信息">
            <n-descriptions :column="3" bordered size="small">
              <n-descriptions-item label="知识库">{{ report.kb_name || '-' }}</n-descriptions-item>
              <n-descriptions-item label="测试集">{{ report.test_set_name || '-' }}</n-descriptions-item>
              <n-descriptions-item label="检索策略">{{ strategyLabel(report.strategy) }}</n-descriptions-item>
              <n-descriptions-item label="Top-K">{{ report.top_k }}</n-descriptions-item>
              <n-descriptions-item label="状态">
                <n-tag :type="statusType(report.status)">{{ statusLabel(report.status) }}</n-tag>
              </n-descriptions-item>
              <n-descriptions-item label="创建时间">{{ formatDate(report.created_at) }}</n-descriptions-item>
            </n-descriptions>

            <n-progress
              v-if="report.status === 'running'"
              type="line"
              :percentage="progressPercentage"
              style="margin-top: 16px"
            />
            <n-alert v-if="report.status === 'failed'" type="error" style="margin-top: 16px">
              {{ report.error_message || '评测执行失败' }}
            </n-alert>
          </n-card>

          <n-card class="section" size="small" title="指标概览">
            <div class="metrics">
              <div class="metric">
                <div class="metric__value">{{ formatPercent(report.metrics?.recall) }}</div>
                <div class="metric__label">Recall@{{ report.top_k }}</div>
              </div>
              <div class="metric">
                <div class="metric__value">{{ formatNumber(report.metrics?.mrr) }}</div>
                <div class="metric__label">MRR</div>
              </div>
              <div class="metric">
                <div class="metric__value">{{ report.metrics?.hit_count || 0 }} / {{ report.metrics?.total || 0 }}</div>
                <div class="metric__label">命中题数</div>
              </div>
            </div>

            <n-alert v-if="compareReport" type="info" :bordered="false" style="margin-top: 16px">
              对比报告：{{ compareReport.kb_name }} / {{ compareReport.test_set_name }}，
              Recall {{ formatPercent(compareReport.metrics?.recall) }}，
              MRR {{ formatNumber(compareReport.metrics?.mrr) }}。
            </n-alert>
          </n-card>

          <n-card class="section" size="small">
            <template #header>
              <n-space align="center" justify="space-between">
                <span>逐题明细</span>
                <n-space>
                  <n-select
                    v-model:value="hitFilter"
                    :options="hitFilterOptions"
                    style="width: 130px"
                  />
                  <n-input
                    v-model:value="searchQuery"
                    placeholder="搜索问题"
                    clearable
                    style="width: 220px"
                  />
                  <n-button :disabled="filteredDetails.length === 0" @click="exportCSV">
                    <template #icon>
                      <n-icon :component="DownloadOutline" />
                    </template>
                    导出 CSV
                  </n-button>
                </n-space>
              </n-space>
            </template>

            <n-data-table
              :columns="columns"
              :data="filteredDetails"
              :pagination="pagination"
              :bordered="true"
              :single-line="false"
              size="small"
            />
          </n-card>
        </template>
      </n-spin>
    </n-layout-content>
  </n-layout>
</template>

<script setup>
import { computed, h, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NDescriptions,
  NDescriptionsItem,
  NEmpty,
  NIcon,
  NInput,
  NLayout,
  NLayoutContent,
  NLayoutHeader,
  NProgress,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  useMessage
} from 'naive-ui'
import { ArrowBackOutline, DownloadOutline } from '@vicons/ionicons5'
import { compareEvaluations, getEvaluation, getEvaluations } from '@/api/zhiyuan'

const route = useRoute()
const router = useRouter()
const message = useMessage()

const loading = ref(false)
const report = ref(null)
const allEvaluations = ref([])
const compareId = ref(null)
const compareReport = ref(null)
const searchQuery = ref('')
const hitFilter = ref('all')
const pagination = { pageSize: 10 }
let pollTimer = null

const hitFilterOptions = [
  { label: '全部', value: 'all' },
  { label: '已命中', value: 'hit' },
  { label: '未命中', value: 'miss' }
]

const compareOptions = computed(() =>
  allEvaluations.value
    .filter((item) => item.id !== route.params.id && item.status === 'done')
    .map((item) => ({
      label: `${item.kb_name || '知识库'} / ${strategyLabel(item.strategy)} / ${formatPercent(item.metrics?.recall)}`,
      value: item.id
    }))
)

const progressPercentage = computed(() => {
  if (!report.value?.progress_total) return 0
  return Math.round((report.value.progress_current || 0) / report.value.progress_total * 100)
})

const filteredDetails = computed(() => {
  let items = report.value?.details || []
  if (hitFilter.value === 'hit') items = items.filter((item) => item.hit)
  if (hitFilter.value === 'miss') items = items.filter((item) => !item.hit)
  const keyword = searchQuery.value.trim().toLowerCase()
  if (keyword) {
    items = items.filter((item) =>
      `${item.question || ''} ${item.expected_source || ''} ${item.expected_answer || ''}`.toLowerCase().includes(keyword)
    )
  }
  return items
})

const columns = [
  { title: '#', key: 'index', width: 56, render: (_row, index) => index + 1 },
  { title: '问题', key: 'question', minWidth: 260 },
  {
    title: '期望来源',
    key: 'expected_source',
    width: 160,
    render: (row) => row.expected_source || '-'
  },
  {
    title: '结果',
    key: 'hit',
    width: 90,
    render: (row) =>
      h(NTag, { type: row.hit ? 'success' : 'error', size: 'small' }, { default: () => (row.hit ? '命中' : '未命中') })
  },
  { title: '排名', key: 'rank', width: 70, render: (row) => row.rank || '-' },
  { title: '分数', key: 'score', width: 90, render: (row) => formatNumber(row.score) },
  {
    title: '匹配片段',
    key: 'matched_chunk',
    minWidth: 280,
    render: (row) => h('div', { class: 'chunk' }, row.matched_chunk || '-')
  }
]

async function loadReport() {
  loading.value = true
  try {
    const [reportData, evalData] = await Promise.all([
      getEvaluation(route.params.id),
      getEvaluations()
    ])
    report.value = reportData
    allEvaluations.value = evalData
  } catch (error) {
    message.error(`加载报告失败：${error.message}`)
  } finally {
    loading.value = false
  }
}

watch(compareId, async (nextId) => {
  compareReport.value = null
  if (!nextId) return
  try {
    const result = await compareEvaluations(route.params.id, nextId)
    compareReport.value = result.eval_2
  } catch (error) {
    message.error(`加载对比报告失败：${error.message}`)
  }
})

function exportCSV() {
  const rows = [
    ['question', 'expected_source', 'expected_answer', 'hit', 'rank', 'score', 'matched_chunk'],
    ...filteredDetails.value.map((item) => [
      item.question || '',
      item.expected_source || '',
      item.expected_answer || '',
      item.hit ? '1' : '0',
      item.rank || '',
      item.score || '',
      item.matched_chunk || ''
    ])
  ]
  const csv = rows.map((row) => row.map(csvCell).join(',')).join('\n')
  const blob = new Blob([`\ufeff${csv}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `evaluation_${route.params.id}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

function csvCell(value) {
  return `"${String(value).replaceAll('"', '""')}"`
}

function statusType(status) {
  if (status === 'done') return 'success'
  if (status === 'failed') return 'error'
  if (status === 'running') return 'info'
  return 'default'
}

function statusLabel(status) {
  const map = { running: '运行中', done: '已完成', failed: '失败' }
  return map[status] || status || '-'
}

function strategyLabel(strategy) {
  const map = { hybrid: '混合检索', bm25: 'BM25F', vector: '向量检索' }
  return map[strategy] || strategy || '-'
}

function formatPercent(value) {
  if (typeof value !== 'number') return '-'
  return `${(value * 100).toFixed(1)}%`
}

function formatNumber(value) {
  if (typeof value !== 'number') return '-'
  return value.toFixed(4)
}

function formatDate(value) {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN')
}

onMounted(async () => {
  await loadReport()
  pollTimer = window.setInterval(() => {
    if (report.value?.status === 'running') loadReport()
  }, 2500)
})

onUnmounted(() => {
  if (pollTimer) window.clearInterval(pollTimer)
})
</script>

<style scoped>
.page {
  height: 100%;
  padding: 20px;
  background: transparent;
}

.page__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
  background: transparent;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page__header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
}

.page__header p {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 13px;
}

.page__content {
  background: transparent;
}

.section {
  margin-bottom: 16px;
}

.metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.metric {
  padding: 16px;
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.metric__value {
  font-size: 26px;
  font-weight: 700;
  color: #1d4ed8;
}

.metric__label {
  margin-top: 4px;
  color: #64748b;
  font-size: 13px;
}

.chunk {
  max-height: 88px;
  overflow: auto;
  color: #475569;
  line-height: 1.5;
  white-space: pre-wrap;
}
</style>
