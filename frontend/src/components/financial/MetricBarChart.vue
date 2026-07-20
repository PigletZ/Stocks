<template>
  <div class="metric-bar panel">
    <div class="mb-header">
      <h3>规模对比</h3>
      <select v-model="metricKey">
        <option value="revenue">营业总收入</option>
        <option value="net_profit">归母净利润</option>
        <option value="ncf">经营现金流净额</option>
      </select>
    </div>
    <div ref="chartEl" class="chart"></div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import type { FinStockCompare } from '../../api/client'

const props = defineProps<{ stocks: FinStockCompare[] }>()

const metricKey = ref<'revenue' | 'net_profit' | 'ncf'>('revenue')
const chartEl = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null

const COLORS = ['#60a5fa', '#f59e0b', '#4ade80', '#f87171', '#c084fc', '#22d3ee', '#fb923c', '#a3e635', '#e879f9', '#94a3b8']

// 所有股票展示期并集（旧→新）
const periods = computed(() => {
  const set = new Set<string>()
  props.stocks.forEach((s) => s.periods.forEach((p) => set.add(p)))
  return Array.from(set).sort()
})

function render() {
  if (!chartEl.value) return
  if (!chart) chart = echarts.init(chartEl.value)
  chart.setOption({
    color: COLORS,
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v: number) => (v === null || v === undefined ? '-' : (v / 1e8).toFixed(2) + ' 亿'),
    },
    legend: { bottom: 0, textStyle: { color: '#9ca3af', fontSize: 11 }, itemWidth: 12, itemHeight: 8 },
    grid: { left: 70, right: 16, top: 24, bottom: 48 },
    xAxis: {
      type: 'category',
      data: periods.value,
      axisLine: { lineStyle: { color: '#374151' } },
      axisLabel: { color: '#9ca3af', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        color: '#9ca3af',
        fontSize: 11,
        formatter: (v: number) => (v / 1e8).toFixed(0),
      },
      splitLine: { lineStyle: { color: '#1f2937' } },
    },
    series: props.stocks.map((s) => ({
      name: s.name,
      type: 'bar',
      barMaxWidth: 28,
      data: periods.value.map((p) => {
        const v = s.metrics[p]?.[metricKey.value]
        return v === null || v === undefined ? null : v
      }),
    })),
  })
}

function onResize() {
  chart?.resize()
}

onMounted(() => {
  render()
  window.addEventListener('resize', onResize)
})

watch([() => props.stocks, metricKey], render, { deep: true })

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.panel {
  background: #111827;
  border: 1px solid #1f2937;
  border-radius: 8px;
  padding: 14px 16px;
}

.mb-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

h3 {
  color: #e5e7eb;
  font-size: 15px;
  margin: 0;
}

select {
  background: #1f2937;
  border: 1px solid #374151;
  border-radius: 4px;
  color: #e5e7eb;
  font-size: 13px;
  padding: 4px 8px;
}

.chart {
  width: 100%;
  height: 300px;
}
</style>
