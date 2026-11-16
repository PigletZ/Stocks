<template>
  <div v-if="!history.length" class="empty">暂无历史统计</div>
  <div ref="container" class="chart" role="img" aria-label="市场广度、成交额和涨跌停三组趋势图"></div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import type { DashboardSnapshot } from '../../api/client'
const props = defineProps<{ history: DashboardSnapshot[]; range: number }>()
const container = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
let observer: ResizeObserver | null = null
function update() {
  if (!chart) return
  const compact = (container.value?.clientWidth || 0) < 900
  if (container.value) container.value.style.height = compact ? '590px' : '245px'
  chart.resize()
  const rows = props.history.slice(-props.range)
  const dates = rows.map(r => r.date)
  const axis = (gridIndex: number) => ({ type: 'category' as const, gridIndex, data: dates, boundaryGap: true, axisLabel: { color: '#9ca3af', formatter: (v: string) => v.slice(5) }, axisLine: { lineStyle: { color: '#374151' } } })
  const yAxis = (gridIndex: number, name: string, max?: number) => ({ type: 'value' as const, gridIndex, name, min: 0, max, nameTextStyle: { color: '#9ca3af' }, axisLabel: { color: '#9ca3af' }, splitLine: { lineStyle: { color: '#374151' } } })
  chart.setOption({
    animation: false,
    title: [
      { text: '市场广度 · 上涨占比', top: 0, left: 8, textStyle: { color: '#d1d5db', fontSize: 13, fontWeight: 500 } },
      { text: '量能 · 全市场成交额', top: compact ? 190 : 0, left: compact ? 8 : '35%', textStyle: { color: '#d1d5db', fontSize: 13, fontWeight: 500 } },
      { text: '短线情绪 · 涨停与跌停', top: compact ? 380 : 0, left: compact ? 8 : '69%', textStyle: { color: '#d1d5db', fontSize: 13, fontWeight: 500 } },
    ],
    grid: compact
      ? [{ left: 58, right: 24, top: 42, height: 120 }, { left: 58, right: 24, top: 232, height: 120 }, { left: 58, right: 24, top: 422, height: 120 }]
      : [{ left: '4%', width: '25%', top: 42, height: 150 }, { left: '39%', width: '25%', top: 42, height: 150 }, { left: '73%', width: '25%', top: 42, height: 150 }],
    tooltip: { trigger: 'axis', valueFormatter: (v: unknown) => typeof v === 'number' ? v.toFixed(1) : '—' },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    legend: { bottom: 0, textStyle: { color: '#9ca3af' }, data: ['上涨占比(%)', '成交额(亿)', '涨停(家)', '跌停(家)'] },
    xAxis: [axis(0), axis(1), axis(2)],
    yAxis: [yAxis(0, '%', 100), yAxis(1, '亿元'), yAxis(2, '家')],
    series: [
      { name: '上涨占比(%)', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: rows.map(r => r.up_ratio), connectNulls: false, itemStyle: { color: '#60a5fa' }, markLine: { silent: true, symbol: 'none', label: { show: false }, lineStyle: { color: '#6b7280', type: 'dashed' }, data: [{ yAxis: 50 }] } },
      { name: '成交额(亿)', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: rows.map(r => r.total_turnover == null ? null : r.total_turnover / 1e8), itemStyle: { color: '#60a5fa' }, barMaxWidth: 24 },
      { name: '涨停(家)', type: 'line', xAxisIndex: 2, yAxisIndex: 2, data: rows.map(r => r.limit_up), itemStyle: { color: '#ef4444' } },
      { name: '跌停(家)', type: 'line', xAxisIndex: 2, yAxisIndex: 2, data: rows.map(r => r.limit_down), itemStyle: { color: '#22c55e' } },
    ],
  }, true)
}
onMounted(() => {
  if (!container.value) return
  chart = echarts.init(container.value)
  let lastWidth = 0
  observer = new ResizeObserver(entries => {
    const width = entries[0]?.contentRect.width || 0
    if (width !== lastWidth) { lastWidth = width; update() }
  })
  observer.observe(container.value)
  update()
})
watch(() => [props.history, props.range], update)
onUnmounted(() => { observer?.disconnect(); chart?.dispose() })
</script>

<style scoped>
.chart { width:100%; height:590px; }.empty { padding:20px; text-align:center; color:#9ca3af; font-size:13px; }
</style>
