<template>
  <n-layout class="page">
    <n-layout-header class="page__header">
      <div>
        <h2>评测中心</h2>
        <p>基于测试集评估当前知识库的证据召回能力，第一版聚焦 Recall 与 MRR。</p>
      </div>
      <n-button type="primary" @click="openCreateModal">
        <template #icon>
          <n-icon :component="PlayOutline" />
        </template>
        新建评测
      </n-button>
    </n-layout-header>

    <n-layout-content class="page__content">
      <n-space class="toolbar" align="center" justify="space-between">
        <n-space>
          <n-input
            v-model:value="filterKeyword"
            placeholder="搜索知识库或测试集"
            clearable
            style="width: 240px"
          >
            <template #prefix>
              <n-icon :component="SearchOutline" />
            </template>
          </n-input>
          <n-select
            v-model:value="filterStatus"
            :options="statusFilterOptions"
            style="width: 140px"
          />
        </n-space>
        <n-button tertiary @click="loadAll">刷新</n-button>
      </n-space>

      <n-spin :show="loading">
        <n-empty v-if="!loading && filteredEvaluations.length === 0" description="暂无评测记录">
          <template #extra>
            <n-button type="primary" @click="openCreateModal">新建评测</n-button>
          </template>
        </n-empty>
        <n-data-table
          v-else
          :columns="columns"
          :data="filteredEvaluations"
          :pagination="pagination"
          :bordered="true"
          :single-line="false"
          size="small"
        />
      </n-spin>
    </n-layout-content>

    <n-modal
      v-model:show="showCreateModal"
      preset="card"
      title="新建评测"
      style="width: 560px"
      :mask-closable="false"
    >
      <n-form :model="form" label-placement="left" label-width="96px">
        <n-form-item label="知识库" required>
          <n-select
            v-model:value="form.kb_id"
            :options="kbOptions"
            placeholder="选择知识库"
            filterable
          />
        </n-form-item>
        <n-form-item label="测试集" required>
          <n-select
            v-model:value="form.test_set_id"
            :options="testSetOptions"
            placeholder="选择测试集"
            filterable
          />
        </n-form-item>
        <n-form-item label="检索策略">
          <n-select v-model:value="form.strategy" :options="strategyOptions" />
        </n-form-item>
        <n-form-item label="Top-K">
          <n-input-number v-model:value="form.top_k" :min="1" :max="50" />
        </n-form-item>
      </n-form>

      <n-alert type="info" :bordered="false" style="margin-top: 8px">
        当前评测会调用 FinLongRAG 的检索链路，生成检索级报告。答案级 LLM Judge 可以在后续接入。
      </n-alert>

      <template #footer>
        <n-space justify="end">
          <n-button @click="showCreateModal = false">取消</n-button>
          <n-button type="primary" :disabled="!canCreate" :loading="creating" @click="handleCreate">
            开始评测
          </n-button>
        </n-space>
      </template>
    </n-modal>
  </n-layout>
</template>

<script setup>
import { computed, h, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  NAlert,
  NButton,
  NDataTable,
  NEmpty,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NInputNumber,
  NLayout,
  NLayoutContent,
  NLayoutHeader,
  NModal,
  NPopconfirm,
  NProgress,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  useMessage
} from 'naive-ui'
import { PlayOutline, SearchOutline } from '@vicons/ionicons5'
import {
  createEvaluation,
  deleteEvaluation,
  getEvaluations,
  getKnowledgeBases,
  getTestSets
} from '@/api/zhiyuan'
import { evalFormatDate, evalFormatNumber, evalFormatPercent, evalStatusLabel, evalStatusType, evalStrategyLabel } from '@/utils/formatters'

const router = useRouter()
const message = useMessage()

const loading = ref(false)
const creating = ref(false)
const showCreateModal = ref(false)
const filterKeyword = ref('')
const filterStatus = ref('all')
const evaluations = ref([])
const knowledgeBases = ref([])
const testSets = ref([])

const form = reactive({
  kb_id: null,
  test_set_id: null,
  strategy: 'hybrid',
  top_k: 8
})

const pagination = reactive({ pageSize: 15 })
let pollTimer = null

const statusFilterOptions = [
  { label: '全部状态', value: 'all' },
  { label: '运行中', value: 'running' },
  { label: '已完成', value: 'done' },
  { label: '失败', value: 'failed' }
]

const strategyOptions = [
  { label: '混合检索（BM25F + 向量融合）', value: 'hybrid' },
  { label: 'BM25F 关键词检索', value: 'bm25' },
  { label: '向量检索（需启用 pgvector）', value: 'vector' }
]

const kbOptions = computed(() =>
  knowledgeBases.value.map((item) => ({
    label: item.name,
    value: item.id
  }))
)

const testSetOptions = computed(() =>
  testSets.value.map((item) => ({
    label: `${item.name}（${item.count || 0}题）`,
    value: item.id
  }))
)

const canCreate = computed(() => Boolean(form.kb_id && form.test_set_id && form.top_k))

const filteredEvaluations = computed(() => {
  const keyword = filterKeyword.value.trim().toLowerCase()
  return evaluations.value.filter((item) => {
    const statusMatched = filterStatus.value === 'all' || item.status === filterStatus.value
    const keywordMatched =
      !keyword ||
      `${item.kb_name || ''} ${item.test_set_name || ''} ${item.strategy || ''}`.toLowerCase().includes(keyword)
    return statusMatched && keywordMatched
  })
})

const columns = [
  { title: '知识库', key: 'kb_name', minWidth: 160 },
  { title: '测试集', key: 'test_set_name', minWidth: 180 },
  {
    title: '策略',
    key: 'strategy',
    width: 130,
    render: (row) => evalStrategyLabel(row.strategy)
  },
  { title: 'Top-K', key: 'top_k', width: 80 },
  {
    title: '状态',
    key: 'status',
    width: 190,
    render: (row) => {
      const nodes = [
        h(NTag, { type: evalStatusType(row.status), size: 'small' }, { default: () => evalStatusLabel(row.status) })
      ]
      if (row.status === 'running') {
        const percentage = row.progress_total
          ? Math.round((row.progress_current || 0) / row.progress_total * 100)
          : 0
        nodes.push(h(NProgress, { type: 'line', percentage, height: 8, showIndicator: false }))
      }
      return h(NSpace, { vertical: true, size: 4 }, { default: () => nodes })
    }
  },
  {
    title: '指标',
    key: 'metrics',
    width: 170,
    render: (row) => {
      if (row.status !== 'done') return '-'
      const metrics = row.metrics || {}
      return `Recall ${evalFormatPercent(metrics.recall)} / MRR ${evalFormatNumber(metrics.mrr)}`
    }
  },
  {
    title: '创建时间',
    key: 'created_at',
    width: 180,
    render: (row) => evalFormatDate(row.created_at)
  },
  {
    title: '操作',
    key: 'actions',
    width: 180,
    render: (row) =>
      h(NSpace, { size: 8 }, {
        default: () => [
          h(NButton, { size: 'small', onClick: () => router.push(`/evaluations/${row.id}`) }, { default: () => '报告' }),
          h(
            NPopconfirm,
            { positiveText: '删除', negativeText: '取消', onPositiveClick: () => handleDelete(row.id) },
            {
              trigger: () => h(NButton, { size: 'small', type: 'error', ghost: true }, { default: () => '删除' }),
              default: () => '确认删除这次评测记录？'
            }
          )
        ]
      })
  }
]

async function loadAll() {
  loading.value = true
  try {
    const [kbData, testSetData, evalData] = await Promise.all([
      getKnowledgeBases(),
      getTestSets(),
      getEvaluations()
    ])
    knowledgeBases.value = kbData
    testSets.value = testSetData
    evaluations.value = evalData
    if (!form.kb_id && kbData.length) form.kb_id = kbData[0].id
    if (!form.test_set_id && testSetData.length) form.test_set_id = testSetData[0].id
  } catch (error) {
    message.error(`加载评测数据失败：${error.message}`)
  } finally {
    loading.value = false
  }
}

async function loadEvaluations() {
  try {
    evaluations.value = await getEvaluations()
  } catch (error) {
    console.warn('Failed to refresh evaluations:', error)
  }
}

function openCreateModal() {
  if (!form.kb_id && knowledgeBases.value.length) form.kb_id = knowledgeBases.value[0].id
  if (!form.test_set_id && testSets.value.length) form.test_set_id = testSets.value[0].id
  showCreateModal.value = true
}

async function handleCreate() {
  creating.value = true
  try {
    const result = await createEvaluation({
      kb_id: form.kb_id,
      test_set_id: form.test_set_id,
      strategy: form.strategy,
      top_k: form.top_k
    })
    message.success('评测任务已创建')
    showCreateModal.value = false
    await loadEvaluations()
    if (result?.id) {
      router.push(`/evaluations/${result.id}`)
    }
  } catch (error) {
    message.error(`创建评测失败：${error.message}`)
  } finally {
    creating.value = false
  }
}

async function handleDelete(id) {
  try {
    await deleteEvaluation(id)
    message.success('评测记录已删除')
    await loadEvaluations()
  } catch (error) {
    message.error(`删除失败：${error.message}`)
  }
}

onMounted(async () => {
  await loadAll()
  pollTimer = window.setInterval(() => {
    if (!document.hidden) loadEvaluations()
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

.page__header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
}

.page__header p {
  margin: 6px 0 0;
  color: var(--text-4);
  font-size: 13px;
}

.page__content {
  padding: 16px;
  background: var(--surface-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
}

.toolbar {
  margin-bottom: 16px;
}
</style>
