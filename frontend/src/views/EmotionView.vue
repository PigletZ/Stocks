<template>
  <div class="page">
    <div class="page-header">
      <h1>情绪周期</h1>
      <div class="actions">
        <button
          v-for="range in quickRanges"
          :key="range.label"
          class="toggle-btn"
          :class="{ active: activeRange === range.label }"
          @click="setQuickRange(range)"
        >
          {{ range.label }}
        </button>
      </div>
    </div>

    <div v-if="error" class="error-message">{{ error }}</div>
    <div v-if="loading" class="loading-text">加载中...</div>

    <template v-else>
      <!-- 最新一日情绪摘要 -->
      <div v-if="latest" class="stats-row">
        <div class="stat-card">
          <div class="stat-label">{{ latest.date }} 涨停 / 跌停</div>
          <div class="stat-value">
            <span class="up">{{ latest.limit_up }}</span> / <span class="down">{{ latest.limit_down }}</span>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-label">炸板率</div>
          <div class="stat-value" :class="(latest.break_rate ?? 0) >= 40 ? 'down' : ''">
            {{ latest.break_rate !== null ? latest.break_rate + '%' : '-' }}
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-label">晋级率</div>
          <div class="stat-value" :class="(latest.promote_rate ?? 0) >= 30 ? 'up' : ''">
            {{ latest.promote_rate !== null ? latest.promote_rate + '%' : '-' }}
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-label">最高板</div>
          <div class="stat-value up">{{ latest.max_board }} 板</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">两市成交额</div>
          <div class="stat-value">{{ formatTurnover(latest.total_turnover) }}</div>
        </div>
      </div>

      <!-- 涨停/跌停/最高板 -->
      <div class="panel">
        <div class="panel-title">涨跌停与最高板</div>
        <div ref="countChart" class="chart"></div>
      </div>

      <!-- 炸板率/晋级率 -->
      <div class="panel">
        <div class="panel-title">炸板率与晋级率（短线赚钱效应）</div>
        <div ref="rateChart" class="chart"></div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts'
import { fetchEmotionSeries, type EmotionItem } from '../api/client'

const items = ref<EmotionItem[]>([])
const loading = ref(false)
const error = ref('')
const activeRange = ref('近三月')
const countChart = ref<HTMLElement | null>(null)
const rateChart = ref<HTMLElement | null>(null)
let countInstance: echarts.ECharts | null = null
let rateInstance: echarts.ECharts | null = null

const quickRanges = [
  { label: '近一月', days: 29 },
  { label: '近三月', days: 89 },
  { label: '近六月', days: 182 },
  { label: '近一年', days: 365 },
  { label: '全部', days: 0 },
]

const latest = computed(() => (items.value.length ? items.value[items.value.length - 1] : null))

function formatDate(d: Date) {
  return d.toISOString().slice(0, 10)
}

function formatTurnover(v: number) {
  return (v / 1e8).toFixed(0) + ' 亿'
}

function baseOption(dates: string[], series: echarts.SeriesOption[], yName = ''): echarts.EChartsOption {
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: { data: series.map((s) => s.name as string), textStyle: { color: '#9ca3af' }, bottom: 0 },
    grid: { left: 50, right: 20, top: 20, bottom: 40 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLine: { lineStyle: { color: '#374151' } },
      axisLabel: { color: '#9ca3af' },
    },
    yAxis: {
      type: 'value',
      name: yName,
      axisLine: { lineStyle: { color: '#374151' } },
      axisLabel: { color: '#9ca3af' },
      splitLine: { lineStyle: { color: '#374151' } },
    },
    series,
  }
}

function renderCharts() {
  if (!countChart.value || !rateChart.value || items.value.length === 0) return
  countInstance = countInstance || echarts.init(countChart.value)
  rateInstance = rateInstance || echarts.init(rateChart.value)

  const dates = items.value.map((i) => i.date)

  countInstance.setOption(
    baseOption(dates, [
      {
        name: '涨停数',
        type: 'line',
        data: items.value.map((i) => i.limit_up),
        smooth: true,
        itemStyle: { color: '#ef4444' },
        areaStyle: { opacity: 0.08 },
      },
      {
        name: '跌停数',
        type: 'line',
        data: items.value.map((i) => i.limit_down),
        smooth: true,
        itemStyle: { color: '#22c55e' },
        areaStyle: { opacity: 0.08 },
      },
      {
        name: '最高板',
        type: 'bar',
        data: items.value.map((i) => i.max_board),
        itemStyle: { color: '#f59e0b', opacity: 0.6 },
        barMaxWidth: 6,
      },
    ])
  )

  rateInstance.setOption(
    baseOption(
      dates,
      [
        {
          name: '炸板率%',
          type: 'line',
          data: items.value.map((i) => i.break_rate),
          smooth: true,
          itemStyle: { color: '#a855f7' },
          areaStyle: { opacity: 0.08 },
        },
        {
          name: '晋级率%',
          type: 'line',
          data: items.value.map((i) => i.promote_rate),
          smooth: true,
          itemStyle: { color: '#f97316' },
          areaStyle: { opacity: 0.08 },
        },
      ],
      '%'
    )
  )
}

async function load(start?: string, end?: string) {
  // loading 期间图表容器会被 v-if 卸载，必须先销毁绑在旧 DOM 上的实例
  countInstance?.dispose()
  countInstance = null
  rateInstance?.dispose()
  rateInstance = null
  loading.value = true
  error.value = ''
  try {
    items.value = await fetchEmotionSeries(start, end)
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载失败'
  } finally {
    // 必须先置回 false 让图表容器挂载（v-else），再渲染图表
    loading.value = false
  }
  await nextTick()
  renderCharts()
}

function setQuickRange(range: { label: string; days: number }) {
  activeRange.value = range.label
  if (range.days === 0) {
    load('2024-01-02', formatDate(new Date()))
  } else {
    const end = new Date()
    const start = new Date(Date.now() - range.days * 24 * 60 * 60 * 1000)
    load(formatDate(start), formatDate(end))
  }
}

function onResize() {
  countInstance?.resize()
  rateInstance?.resize()
}

onMounted(() => {
  setQuickRange(quickRanges[1])
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  countInstance?.dispose()
  rateInstance?.dispose()
})
</script>

<style scoped>
.page {
  padding: 20px;
  max-width: 1400px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.page-header h1 {
  font-size: 20px;
  color: #e5e7eb;
}

.actions {
  display: flex;
  gap: 8px;
}

.toggle-btn {
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid #374151;
  background: #1f2937;
  color: #9ca3af;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.toggle-btn.active {
  background: #2563eb;
  border-color: #2563eb;
  color: #fff;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.stat-card {
  background: #1f2937;
  border-radius: 10px;
  padding: 14px 18px;
}

.stat-label {
  font-size: 12px;
  color: #9ca3af;
  margin-bottom: 6px;
}

.stat-value {
  font-size: 20px;
  font-weight: 600;
  color: #e5e7eb;
}

.up { color: #ef4444; }
.down { color: #22c55e; }

.panel {
  background: #1f2937;
  border-radius: 10px;
  padding: 18px;
  margin-bottom: 16px;
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: #d1d5db;
  margin-bottom: 10px;
}

.chart {
  width: 100%;
  height: 320px;
}

.loading-text {
  color: #9ca3af;
  padding: 40px;
  text-align: center;
}

.error-message {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.4);
  color: #ef4444;
  border-radius: 8px;
  padding: 10px 14px;
  margin-bottom: 16px;
}
</style>
