<template>
  <div class="emotion-history">
    <div class="range-bar"><span>截至 {{ asOf }} · 点击数据点切换当天复盘</span><div class="ranges"><button v-for="range in quickRanges" :key="range.label" :class="{ active: activeRange === range.label }" @click="setQuickRange(range)">{{ range.label }}</button></div></div>
    <p class="note">涨跌停家数与最高板使用独立纵轴。炸板率和涨停延续率为价格状态统计，不代表实际收益；缺失值留空。</p>
    <p v-if="error" class="error" role="alert">{{ error }} <button @click="setQuickRange(quickRanges.find(r => r.label === activeRange) || quickRanges[0])">重试</button></p>
    <p v-if="loading" class="empty">正在加载情绪历史…</p>
    <template v-else>
      <p v-if="!items.length && !error" class="empty">截至所选日期暂无历史数据</p>
      <div class="chart-grid">
        <section><h3>涨跌停与连板高度</h3><div ref="countChart" class="chart" role="img" aria-label="涨跌停家数与最高连板趋势"></div></section>
        <section><h3>炸板与涨停延续</h3><div ref="rateChart" class="chart" role="img" aria-label="炸板率与涨停延续率趋势"></div></section>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from '../../utils/charts'
import { fetchEmotionSeries, type EmotionItem } from '../../api/client'

const items = ref<EmotionItem[]>([])
const props = defineProps<{ asOf: string; rangeDays?: number }>()
const emit = defineEmits<{ selectDate: [date: string]; rangeChange: [days: number] }>()
let requestId = 0
const loading = ref(false)
const error = ref('')
const activeRange = ref('近一月')
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

function formatDate(d: Date) {
  return d.toISOString().slice(0, 10)
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
  for (const chart of [countInstance, rateInstance]) {
    chart.off('click')
    chart.on('click', (point) => {
      if (typeof point.name === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(point.name)) emit('selectDate', point.name)
    })
  }

  const dates = items.value.map((i) => i.date)

  countInstance.setOption(
    { ...baseOption(dates, [
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
        yAxisIndex: 1,
        data: items.value.map((i) => i.max_board),
        itemStyle: { color: '#f59e0b', opacity: 0.6 },
        barMaxWidth: 6,
      },
    ]), yAxis: [
      { type: 'value', name: '家', axisLabel: {color: '#9ca3af'}, splitLine: {lineStyle: {color: '#374151'}} },
      { type: 'value', name: '板', min:0, minInterval:1, axisLabel: {color: '#9ca3af'}, splitLine: {show:false} }
    ], grid: {left:50,right:45,top:30,bottom:40} }
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
  const request = ++requestId
  // loading 期间图表容器会被 v-if 卸载，必须先销毁绑在旧 DOM 上的实例
  countInstance?.dispose()
  countInstance = null
  rateInstance?.dispose()
  rateInstance = null
  loading.value = true
  error.value = ''
  items.value = []
  try {
    const result = await fetchEmotionSeries(start, end)
    if (request !== requestId) return
    items.value = result.filter(row => row.date <= props.asOf)
  } catch (err: any) {
    if (request !== requestId) return
    error.value = err?.response?.data?.detail || '加载失败'
  } finally {
    // 必须先置回 false 让图表容器挂载（v-else），再渲染图表
    if (request === requestId) loading.value = false
  }
  if (request !== requestId) return
  await nextTick()
  renderCharts()
}

function setQuickRange(range: { label: string; days: number }) {
  activeRange.value = range.label
  emit('rangeChange', range.days)
  if (range.days === 0) {
    load('2024-01-02', props.asOf)
  } else {
    const end = new Date(`${props.asOf}T12:00:00`)
    const start = new Date(end.getTime() - range.days * 24 * 60 * 60 * 1000)
    load(formatDate(start), props.asOf)
  }
}

function onResize() {
  countInstance?.resize()
  rateInstance?.resize()
}

onMounted(() => {
  setQuickRange(quickRanges.find(range => range.days === props.rangeDays) || quickRanges[0])
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  requestId++
  window.removeEventListener('resize', onResize)
  countInstance?.dispose()
  rateInstance?.dispose()
})
watch(() => props.asOf, () => {
  const selected = quickRanges.find(range => range.label === activeRange.value) || quickRanges[0]
  setQuickRange(selected)
})
</script>

<style scoped>
.range-bar,.ranges { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }.range-bar { justify-content:space-between; color:#9ca3af; font-size:12px; margin-top:16px; }.ranges button,button { background:#111827; border:1px solid #374151; color:#d1d5db; border-radius:6px; padding:6px 10px; cursor:pointer; }.ranges .active { background:#172554; border-color:#60a5fa; color:#fff; }.note { color:#9ca3af; font-size:12px; line-height:1.8; }.chart-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:20px; }h3 { color:#d1d5db; font-size:14px; font-weight:500; margin:12px 0; }.chart { height:300px; width:100%; }.error { color:#fca5a5; font-size:13px; }.empty { color:#9ca3af; font-size:13px; text-align:center; padding:20px; }@media(max-width:1000px) { .chart-grid { grid-template-columns:1fr; } }
</style>
