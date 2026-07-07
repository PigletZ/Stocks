<template>
  <div ref="chartContainer" class="equity-chart"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { createChart } from 'lightweight-charts'
import type { ISeriesApi, IChartApi, LineData } from 'lightweight-charts'
import type { EquityPoint } from '../../api/client'

const props = defineProps<{
  equityCurve: EquityPoint[]
}>()

const chartContainer = ref<HTMLDivElement | null>(null)
let chart: IChartApi | null = null
let equitySeries: ISeriesApi<'Line'> | null = null

function toLineData(point: EquityPoint): LineData {
  return {
    time: point.date as string,
    value: point.total_value,
  }
}

function initChart() {
  if (!chartContainer.value) return

  chart = createChart(chartContainer.value, {
    layout: {
      background: { color: '#111827' },
      textColor: '#e5e7eb',
    },
    grid: {
      vertLines: { color: '#1f2937' },
      horzLines: { color: '#1f2937' },
    },
    rightPriceScale: {
      borderColor: '#1f2937',
    },
    timeScale: {
      borderColor: '#1f2937',
    },
  })

  equitySeries = chart.addLineSeries({
    color: '#2563eb',
    lineWidth: 2,
    title: '总权益',
  })

  chart.timeScale().fitContent()
}

function updateChart() {
  if (!equitySeries || !chart || props.equityCurve.length === 0) return
  const data = props.equityCurve.map(toLineData)
  equitySeries.setData(data)
  chart.timeScale().fitContent()
}

onMounted(() => {
  initChart()
  updateChart()
})

onUnmounted(() => {
  if (chart) {
    chart.remove()
    chart = null
  }
})

watch(() => props.equityCurve, updateChart, { deep: true })
</script>

<style scoped>
.equity-chart {
  width: 100%;
  height: 320px;
  background: #111827;
  border: 1px solid #1f2937;
  border-radius: 8px;
  overflow: hidden;
}
</style>
