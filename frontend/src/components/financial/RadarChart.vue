<template>
  <div class="radar-chart panel">
    <h3>五维对比（相对归一化）</h3>
    <div ref="chartEl" class="chart"></div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps<{
  radar: { dims: string[]; series: { name: string; values: number[] }[] }
}>()

const chartEl = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null

const COLORS = ['#60a5fa', '#f59e0b', '#4ade80', '#f87171', '#c084fc', '#22d3ee', '#fb923c', '#a3e635', '#e879f9', '#94a3b8']

function render() {
  if (!chartEl.value || !props.radar.dims.length) return
  if (!chart) chart = echarts.init(chartEl.value)
  chart.setOption({
    color: COLORS,
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item' },
    legend: {
      bottom: 0,
      textStyle: { color: '#9ca3af', fontSize: 11 },
      itemWidth: 12,
      itemHeight: 8,
    },
    radar: {
      indicator: props.radar.dims.map((d) => ({ name: d, max: 100 })),
      radius: '62%',
      center: ['50%', '46%'],
      axisName: { color: '#d1d5db', fontSize: 12 },
      splitLine: { lineStyle: { color: '#1f2937' } },
      splitArea: { show: false },
      axisLine: { lineStyle: { color: '#1f2937' } },
    },
    series: [
      {
        type: 'radar',
        data: props.radar.series.map((s) => ({
          name: s.name,
          value: s.values,
          areaStyle: { opacity: 0.08 },
          lineStyle: { width: 2 },
          symbolSize: 4,
        })),
      },
    ],
  })
}

function onResize() {
  chart?.resize()
}

onMounted(() => {
  render()
  window.addEventListener('resize', onResize)
})

watch(() => props.radar, render, { deep: true })

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

h3 {
  color: #e5e7eb;
  font-size: 15px;
  margin: 0 0 8px;
}

.chart {
  width: 100%;
  height: 340px;
}
</style>
