<template>
  <div class="financial-view">
    <div class="header">
      <h1>财务分析</h1>
      <nav class="tab-nav">
        <button
          v-for="t in tabs"
          :key="t.key"
          class="tab-btn"
          :class="{ active: activeTab === t.key }"
          @click="activeTab = t.key"
        >{{ t.label }}</button>
      </nav>
    </div>

    <template v-if="activeTab === 'analysis'">
      <StockPicker v-model="picked" />

      <div v-if="error" class="error-banner">{{ error }}</div>
      <div v-if="loading" class="hint">分析中（首次分析需回源拉取财报，稍候）…</div>
      <div v-else-if="!picked.length" class="hint">请选择要分析的股票</div>

      <template v-if="result && !loading">
        <!-- ① 财务体检卡 -->
        <section class="cards-row">
          <HealthCard v-for="s in result.stocks" :key="s.code" :stock="s" />
        </section>

        <!-- ② 多股对比 -->
        <section class="compare-grid">
          <CompareTable :stocks="result.stocks" />
          <RadarChart v-if="result.stocks.length >= 2" :radar="result.radar" />
        </section>
        <section v-if="result.stocks.length >= 2" class="bar-row">
          <MetricBarChart :stocks="result.stocks" />
        </section>

        <!-- ③ 报表原文查看器 -->
        <section class="statement-row">
          <StatementTable :stocks="result.stocks" />
        </section>
      </template>
    </template>

    <HighlightRankTab v-if="activeTab === 'rank'" @compare="onCompare" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import StockPicker from '../components/financial/StockPicker.vue'
import HealthCard from '../components/financial/HealthCard.vue'
import CompareTable from '../components/financial/CompareTable.vue'
import RadarChart from '../components/financial/RadarChart.vue'
import MetricBarChart from '../components/financial/MetricBarChart.vue'
import StatementTable from '../components/financial/StatementTable.vue'
import HighlightRankTab from '../components/financial/HighlightRankTab.vue'
import { fetchFinancialCompare, type FinCompareResult } from '../api/client'

const route = useRoute()
const router = useRouter()

const tabs: { key: 'analysis' | 'rank'; label: string }[] = [
  { key: 'analysis', label: '个股分析' },
  { key: 'rank', label: '亮点榜' },
]
const activeTab = ref<'analysis' | 'rank'>('analysis')

const picked = ref<{ code: string; name: string }[]>([])
const result = ref<FinCompareResult | null>(null)
const loading = ref(false)
const error = ref('')

let reqSeq = 0

async function analyze() {
  const codes = picked.value.map((s) => s.code)
  // 同步 URL，便于刷新/分享保留状态
  router.replace({ query: codes.length ? { codes: codes.join(',') } : {} })
  if (!codes.length) {
    result.value = null
    error.value = ''
    return
  }
  const seq = ++reqSeq
  loading.value = true
  error.value = ''
  try {
    const res = await fetchFinancialCompare(codes)
    if (seq !== reqSeq) return // 已有更新的请求
    result.value = res
    // 用后端返回的标准名称回填 chips（URL 恢复时名称是未知的）；
    // 名称有变化才回填并屏蔽 watch，避免回填再次触发分析形成循环
    const next = res.stocks.map((s) => ({ code: s.code, name: s.name }))
    if (next.some((s, i) => picked.value[i]?.name !== s.name)) {
      restoring = true
      picked.value = next
      restoring = false
    }
  } catch (e: any) {
    if (seq !== reqSeq) return
    result.value = null
    error.value = e?.response?.data?.detail || '分析失败，请稍后重试'
  } finally {
    if (seq === reqSeq) loading.value = false
  }
}

// 选股变化即重新分析（跳过 URL 恢复触发的首次回填）
let restoring = false
watch(picked, () => {
  if (restoring) return
  analyze()
}, { deep: true })

// 亮点榜「加入对比」：加入选股并切回个股分析
function onCompare(stock: { code: string; name: string }) {
  if (!picked.value.some((s) => s.code === stock.code) && picked.value.length < 10) {
    picked.value = [...picked.value, stock]
  }
  activeTab.value = 'analysis'
}

onMounted(async () => {
  const q = route.query.codes
  const codes = (typeof q === 'string' ? q : '').split(',').filter(Boolean).slice(0, 10)
  if (codes.length) {
    restoring = true
    picked.value = codes.map((c) => ({ code: c, name: c }))
    await analyze()
    restoring = false
  }
})
</script>

<style scoped>
.financial-view {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.header {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header h1 {
  color: #ffffff;
  font-size: 20px;
  margin: 0;
}

.tab-nav {
  display: flex;
  gap: 4px;
}

.tab-btn {
  background: #1f2937;
  border: 1px solid #374151;
  border-radius: 4px;
  color: #d1d5db;
  font-size: 13px;
  padding: 5px 14px;
  cursor: pointer;
  transition: all 0.15s;
}

.tab-btn:hover {
  color: #fff;
}

.tab-btn.active {
  background: #2563eb;
  border-color: #2563eb;
  color: #fff;
}

.hint {
  color: #6b7280;
  font-size: 14px;
  text-align: center;
  padding: 60px 0;
}

.error-banner {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.4);
  color: #f87171;
  font-size: 13px;
  padding: 10px 14px;
  border-radius: 6px;
}

.cards-row {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 4px;
}

.compare-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
}

@media (min-width: 1280px) {
  .compare-grid:has(> *:nth-child(2)) {
    grid-template-columns: 3fr 2fr;
  }
}
</style>
