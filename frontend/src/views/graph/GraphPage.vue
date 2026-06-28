<template>
  <div class="fin-analysis-page page-shell">
    <PageHeader
      title="金融数据分析"
      description="面向金融长文本的数值提取、对比分析与趋势洞察。在问答页中选择「数值/对比分析」模式使用此能力。"
    />

    <!-- 概览卡片 -->
    <div class="fin-overview-grid">
      <InfoCard label="知识库总量" :value="kbStore.list.length" caption="当前账号下全部知识库" tone="info" />
      <InfoCard label="已就绪" :value="kbStore.readyCount" caption="完成初始化的知识库数量" tone="muted" />
      <InfoCard label="文档总量" :value="kbStore.documentTotal" caption="累计上传文档数量" tone="muted" />
      <InfoCard label="切块总量" :value="kbStore.chunkTotal" caption="文本切块总量" tone="muted" />
    </div>

    <!-- 分析能力模块 -->
    <div class="fin-capabilities">
      <div class="fin-capabilities__title">支持的分析能力</div>
      <div class="fin-capabilities__grid">
        <div class="fin-cap-card" @click="startQuickChat('请提取这份财报中的关键财务指标，包括营收、净利润、毛利率等')">
          <div class="fin-cap-card__icon fin-cap-card__icon--blue">
            <n-icon size="20" :component="TrendingUpOutline" />
          </div>
          <div class="fin-cap-card__content">
            <div class="fin-cap-card__title">财务指标提取</div>
            <div class="fin-cap-card__desc">从财报、招股书等文档中自动提取营收、利润、增长率等关键指标</div>
          </div>
        </div>
        <div class="fin-cap-card" @click="startQuickChat('请对比分析这两份财务数据，找出主要差异和趋势变化')">
          <div class="fin-cap-card__icon fin-cap-card__icon--purple">
            <n-icon size="20" :component="GitCompareOutline" />
          </div>
          <div class="fin-cap-card__content">
            <div class="fin-cap-card__title">对比分析</div>
            <div class="fin-cap-card__desc">跨文档、跨期对比财务数据，发现异常变动与趋势</div>
          </div>
        </div>
        <div class="fin-cap-card" @click="startQuickChat('请分析这家公司的风险评估，包括财务风险和业务风险')">
          <div class="fin-cap-card__icon fin-cap-card__icon--orange">
            <n-icon size="20" :component="WarningOutline" />
          </div>
          <div class="fin-cap-card__content">
            <div class="fin-cap-card__title">风险分析</div>
            <div class="fin-cap-card__desc">基于文档内容进行财务风险、合规风险与业务风险评估</div>
          </div>
        </div>
        <div class="fin-cap-card" @click="startQuickChat('请汇总这份研究报告的核心观点和投资建议')">
          <div class="fin-cap-card__icon fin-cap-card__icon--green">
            <n-icon size="20" :component="DocumentTextOutline" />
          </div>
          <div class="fin-cap-card__content">
            <div class="fin-cap-card__title">研报摘要</div>
            <div class="fin-cap-card__desc">自动生成研究报告、行业分析的结构化摘要与核心观点</div>
          </div>
        </div>
        <div class="fin-cap-card" @click="startQuickChat('请从以下文档中提取所有数值数据，并进行统计分析')">
          <div class="fin-cap-card__icon fin-cap-card__icon--teal">
            <n-icon size="20" :component="StatsChartOutline" />
          </div>
          <div class="fin-cap-card__content">
            <div class="fin-cap-card__title">数值统计分析</div>
            <div class="fin-cap-card__desc">对文档中的数值进行聚合、排序、占比计算等统计处理</div>
          </div>
        </div>
        <div class="fin-cap-card" @click="startQuickChat('请梳理这条产业链的上下游关系及关键公司')">
          <div class="fin-cap-card__icon fin-cap-card__icon--pink">
            <n-icon size="20" :component="ShuffleOutline" />
          </div>
          <div class="fin-cap-card__content">
            <div class="fin-cap-card__title">产业链分析</div>
            <div class="fin-cap-card__desc">抽取产业链上下游关系，梳理业务逻辑与竞争格局</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 使用提示 -->
    <div class="fin-tip">
      <n-icon size="16" :component="InformationCircleOutline" />
      <span>选择知识库后，在智能问答页中使用「数值/对比分析」或「混合检索」模式进行深入分析。需要先在文档中心上传金融文档。</span>
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { NIcon } from 'naive-ui'
import {
  TrendingUpOutline,
  GitCompareOutline,
  WarningOutline,
  DocumentTextOutline,
  StatsChartOutline,
  ShuffleOutline,
  InformationCircleOutline
} from '@vicons/ionicons5'
import InfoCard from '@/components/common/InfoCard.vue'
import PageHeader from '@/components/layout/PageHeader.vue'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBase'

const router = useRouter()
const kbStore = useKnowledgeBaseStore()

function startQuickChat(question) {
  const kbId = kbStore.list[0]?.id
  const query = kbId ? { q: question, kb: kbId } : { q: question }
  router.push({ path: '/chat', query })
}

onMounted(() => kbStore.fetchList())
</script>

<style scoped>
.fin-overview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 28px;
}

.fin-capabilities__title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-1);
  margin-bottom: 14px;
}

.fin-capabilities__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.fin-cap-card {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 18px;
  background: var(--surface-card);
  border: 1px solid var(--border-color);
  border-radius: 14px;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: var(--shadow-soft);
}

.fin-cap-card:hover {
  border-color: var(--brand-300);
  box-shadow: var(--shadow-glow);
  transform: translateY(-2px);
}

.fin-cap-card__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border-radius: 12px;
  flex-shrink: 0;
}

.fin-cap-card__icon--blue { background: rgba(37, 99, 235, 0.12); color: #2563eb; }
.fin-cap-card__icon--purple { background: rgba(124, 58, 237, 0.12); color: #7c3aed; }
.fin-cap-card__icon--orange { background: rgba(234, 88, 12, 0.12); color: #ea580c; }
.fin-cap-card__icon--green { background: rgba(22, 163, 74, 0.12); color: #16a34a; }
.fin-cap-card__icon--teal { background: rgba(13, 148, 136, 0.12); color: #0d9488; }
.fin-cap-card__icon--pink { background: rgba(219, 39, 119, 0.12); color: #db2777; }

.fin-cap-card__content {
  flex: 1;
  min-width: 0;
}

.fin-cap-card__title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-1);
  margin-bottom: 4px;
}

.fin-cap-card__desc {
  font-size: 12.5px;
  color: var(--text-4);
  line-height: 1.6;
}

.fin-tip {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 24px;
  padding: 14px 16px;
  background: var(--surface-hover);
  border: 1px solid var(--brand-soft-border);
  border-radius: 12px;
  color: var(--text-3);
  font-size: 13px;
  line-height: 1.6;
}

@media (max-width: 1100px) {
  .fin-overview-grid,
  .fin-capabilities__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 700px) {
  .fin-overview-grid,
  .fin-capabilities__grid {
    grid-template-columns: 1fr;
  }
}
</style>
