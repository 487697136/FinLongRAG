<template>
  <n-layout class="page">
    <n-layout-header class="page__header">
      <div>
        <h2>测试集</h2>
        <p>上传金融问答评测样本，统一管理问题、标准答案与期望来源，用于验证检索与证据命中效果。</p>
      </div>
      <n-upload
        :custom-request="handleUpload"
        :show-file-list="false"
        accept=".csv,.xlsx,.xls"
      >
        <n-button type="primary" :loading="uploading">
          <template #icon>
            <n-icon :component="AddOutline" />
          </template>
          上传测试集
        </n-button>
      </n-upload>
    </n-layout-header>

    <n-layout-content class="page__content">
      <n-spin :show="loading">
        <n-empty v-if="!loading && testSets.length === 0" description="暂无测试集">
          <template #extra>
            <n-upload
              :custom-request="handleUpload"
              :show-file-list="false"
              accept=".csv,.xlsx,.xls"
            >
              <n-button type="primary">上传首个测试集</n-button>
            </n-upload>
          </template>
        </n-empty>

        <n-table v-else :bordered="true" :single-line="false" size="small">
          <thead>
            <tr>
              <th>名称</th>
              <th>文件</th>
              <th>Sheet</th>
              <th>问题数</th>
              <th>上传时间</th>
              <th style="width: 120px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in testSets" :key="item.id">
              <td>{{ item.name }}</td>
              <td>{{ item.file_name || '-' }}</td>
              <td>{{ item.sheet_names?.length ? item.sheet_names.join(', ') : '-' }}</td>
              <td>{{ item.count }}</td>
              <td>{{ evalFormatDate(item.created_at) }}</td>
              <td>
                <n-popconfirm
                  positive-text="删除"
                  negative-text="取消"
                  @positive-click="handleDelete(item.id)"
                >
                  <template #trigger>
                    <n-button size="small" type="error" ghost>删除</n-button>
                  </template>
                  删除后关联评测仍会保留结果，但不能重新运行该测试集。确认删除？
                </n-popconfirm>
              </td>
            </tr>
          </tbody>
        </n-table>
      </n-spin>
    </n-layout-content>
  </n-layout>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import {
  NButton,
  NEmpty,
  NIcon,
  NLayout,
  NLayoutContent,
  NLayoutHeader,
  NPopconfirm,
  NSpin,
  NTable,
  NUpload,
  useMessage
} from 'naive-ui'
import { AddOutline } from '@vicons/ionicons5'
import { deleteTestSet, getTestSets, uploadTestSet } from '@/api/api'
import { evalFormatDate } from '@/utils/formatters'

const message = useMessage()
const loading = ref(false)
const uploading = ref(false)
const testSets = ref([])

async function loadTestSets() {
  loading.value = true
  try {
    testSets.value = await getTestSets()
  } catch (error) {
    message.error(`加载测试集失败：${error.message}`)
  } finally {
    loading.value = false
  }
}

async function handleUpload({ file, onFinish, onError }) {
  const rawFile = file?.file
  if (!rawFile) return

  uploading.value = true
  try {
    await uploadTestSet(rawFile)
    message.success('测试集上传成功')
    onFinish?.()
    await loadTestSets()
  } catch (error) {
    message.error(`测试集上传失败：${error.message}`)
    onError?.()
  } finally {
    uploading.value = false
  }
}

async function handleDelete(id) {
  try {
    await deleteTestSet(id)
    message.success('测试集已删除')
    await loadTestSets()
  } catch (error) {
    message.error(`删除失败：${error.message}`)
  }
}

onMounted(loadTestSets)
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
</style>
