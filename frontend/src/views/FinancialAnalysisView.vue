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
        <section class="period-bar">
          <label>统一报告期 <select v-model="selectedPeriod"><option v-for="p in periods" :key="p" :value="p">{{ p }}</option></select></label>
          <span>收入、利润及现金流为年初至报告期末累计值；负债为期末值。</span>
          <span v-if="!commonPeriods.length">所选股票没有共同报告期，缺失项留空。</span>
        </section>
        <!-- ① 财务体检卡 -->
        <section class="cards-row">
          <HealthCard v-for="s in selectedStocks" :key="s.code" :stock="s" />
        </section>

        <!-- ② 多股对比 -->
        <FinancialTrend :stocks="result.stocks" :period="selectedPeriod" />
        <section class="compare-grid"><CompareTable :stocks="selectedStocks" :period="selectedPeriod" /></section>
        <details v-if="selectedStocks.length >= 2" class="detail-panel" @toggle="radarOpen = ($event.target as HTMLDetailsElement).open"><summary>深入对比 · 相对雷达图</summary><p>按当前所选股票归一化，非财务评分；更换股票会改变图形。缺少维度的股票不绘制。</p><RadarChart v-if="radarOpen" :radar="selectedRadar" /></details>

        <!-- ③ 报表原文查看器 -->
        <details class="statement-row detail-panel" @toggle="statementsOpen = ($event.target as HTMLDetailsElement).open"><summary>查看原始三大报表</summary>
          <StatementTable v-if="statementsOpen" :stocks="result.stocks" />
        </details>
      </template>
    </template>

    <HighlightRankTab v-if="activeTab === 'rank'" @compare="onCompare" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import StockPicker from '../components/financial/StockPicker.vue'
import HealthCard from '../components/financial/HealthCard.vue'
import CompareTable from '../components/financial/CompareTable.vue'
import RadarChart from '../components/financial/RadarChart.vue'
import FinancialTrend from '../components/financial/FinancialTrend.vue'
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
const selectedPeriod = ref('')
const radarOpen = ref(false)
const statementsOpen = ref(false)
const periods = computed(() => [...new Set(result.value?.stocks.flatMap(s => s.periods) || [])].sort().reverse())
const commonPeriods = computed(() => periods.value.filter(p => result.value?.stocks.every(s => s.periods.includes(p))))
watch(result, () => { selectedPeriod.value = commonPeriods.value[0] || periods.value[0] || '' })
const selectedStocks = computed(() => (result.value?.stocks || []).map(s => ({ ...s, periods: [selectedPeriod.value], card: { period: selectedPeriod.value, ...s.metrics[selectedPeriod.value] }, tags: s.tags_by_period?.[selectedPeriod.value] || [] })))
const selectedRadar = computed(() => {
  const groups = [{ name: '盈利能力', keys: ['gross_margin','net_margin','roe_annualized'] }, { name: '成长能力', keys: ['revenue_yoy','net_profit_yoy'] }, { name: '偿债能力', keys: ['debt_ratio','current_ratio'] }, { name: '现金流质量', keys: ['ncf_ratio'] }, { name: '运营效率', keys: ['inv_turnover','ar_turnover','asset_turnover'] }]
  const values = selectedStocks.value.map(s => s.card as Record<string, unknown>)
  return { dims: groups.map(g => g.name), series: selectedStocks.value.map((s,i) => ({ name: s.name, values: groups.map(g => {
    const normalized = g.keys.flatMap(key => {
      const v = values[i][key]
      if (typeof v !== 'number') return []
      const samples = values.map(r => r[key]).filter((n): n is number => typeof n === 'number')
      const lo = Math.min(...samples), hi = Math.max(...samples)
      const score = hi === lo ? 50 : (v-lo)/(hi-lo)*100
      return [key === 'debt_ratio' ? 100-score : score]
    })
    return normalized.length ? normalized.reduce((a,b) => a+b,0)/normalized.length : null
  }) })) }
})
const loading = ref(false)
const error = ref('')

let reqSeq = 0

async function analyze() {
  const seq = ++reqSeq
  const codes = picked.value.map((s) => s.code)
  // 同步 URL，便于刷新/分享保留状态
  router.replace({ query: codes.length ? { codes: codes.join(',') } : {} })
  if (!codes.length) {
    loading.value = false
    result.value = null
    error.value = ''
    return
  }
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
watch(() => picked.value.map(s => s.code).join(','), () => {
  if (restoring) return
  analyze()
})

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
.period-bar { display:flex; flex-wrap:wrap; align-items:center; gap:14px; padding:16px 20px; border:1px solid #253045; border-radius:10px; color:#9ca3af; font-size:12px; background:#111827; }
.period-bar select { background:#1f2937; color:#e5e7eb; padding:7px; border:1px solid #374151; border-radius:6px; margin-left:8px; }
.detail-panel { background:#111827; border:1px solid #253045; border-radius:10px; padding:18px; color:#d1d5db; }.detail-panel summary { cursor:pointer; font-size:14px; }.detail-panel p { color:#9ca3af; font-size:12px; }
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
  display: grid;
  grid-template-columns: repeat(auto-fit,minmax(min(100%,360px),1fr));
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
