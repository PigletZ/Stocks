<template>
  <div ref="chartContainer" class="chart-panel"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { createChart } from 'lightweight-charts'
import type { ISeriesApi, IChartApi, CandlestickData, HistogramData, LineData } from 'lightweight-charts'
import type { Bar } from '../api/client'

const props = defineProps<{
  bars: Bar[]
  currentIndex: number
}>()

const chartContainer = ref<HTMLDivElement | null>(null)
let chart: IChartApi | null = null
let candleSeries: ISeriesApi<'Candlestick'> | null = null
let volumeSeries: ISeriesApi<'Histogram'> | null = null
let ma5Series: ISeriesApi<'Line'> | null = null

function toChartData(bar: Bar): CandlestickData {
  return {
    time: bar.timestamp.split('T')[0] as string,
    open: bar.open,
    high: bar.high,
    low: bar.low,
    close: bar.close,
  }
}

function calculateMA(data: CandlestickData[], period: number): LineData[] {
  const result: LineData[] = []
  for (let i = period - 1; i < data.length; i++) {
    let sum = 0
    for (let j = 0; j < period; j++) {
      sum += data[i - j].close
    }
    result.push({
      time: data[i].time,
      value: sum / period,
    })
  }
  return result
}

function initChart() {
  if (!chartContainer.value) return

  chart = createChart(chartContainer.value, {
    layout: {
      background: { color: '#1a2230' },
      textColor: '#e0e6ed',
    },
    grid: {
      vertLines: { color: '#2a3441' },
      horzLines: { color: '#2a3441' },
    },
    rightPriceScale: {
      borderColor: '#2a3441',
    },
    timeScale: {
      borderColor: '#2a3441',
    },
  })

  candleSeries = chart.addCandlestickSeries({
    upColor: '#ef4444',
    downColor: '#22c55e',
    borderUpColor: '#ef4444',
    borderDownColor: '#22c55e',
    wickUpColor: '#ef4444',
    wickDownColor: '#22c55e',
  })

  volumeSeries = chart.addHistogramSeries({
    color: '#3b82f6',
    priceFormat: { type: 'volume' },
    priceScaleId: '',
  })
  volumeSeries.priceScale().applyOptions({
    scaleMargins: { top: 0.8, bottom: 0 },
  })

  ma5Series = chart.addLineSeries({
    color: '#f59e0b',
    lineWidth: 1,
  })

  chart.timeScale().fitContent()
}

function updateChart() {
  if (!candleSeries || !volumeSeries || !ma5Series || !chart) return

  const visible = props.bars.slice(0, props.currentIndex + 1)
  const candleData = visible.map(toChartData)
  const volumeData: HistogramData[] = visible.map((bar) => ({
    time: bar.timestamp.split('T')[0] as string,
    value: bar.volume,
    color: bar.close >= bar.open ? '#ef4444' : '#22c55e',
  }))

  candleSeries.setData(candleData)
  volumeSeries.setData(volumeData)
  ma5Series.setData(calculateMA(candleData, 5))
  chart.timeScale().fitContent()
}

onMounted(() => {
  initChart()
  updateChart()
})

onUnmounted(() => {
  chart?.remove()
})

watch(() => [props.bars, props.currentIndex], updateChart, { deep: true })
</script>

<style scoped>
.chart-panel {
  flex: 1;
  min-height: 0;
  border-radius: 4px;
  overflow: hidden;
}
</style>
