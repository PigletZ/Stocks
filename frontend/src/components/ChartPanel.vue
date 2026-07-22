<template>
  <div ref="chartContainer" class="chart-panel">
    <div
      v-if="tooltipVisible"
      ref="tooltipEl"
      class="custom-tooltip"
      :style="tooltipStyle"
    >
      <div class="tooltip-date">{{ tooltipData?.time }}</div>
      <div class="tooltip-row">
        <span>开</span><span>{{ formatPrice(tooltipData?.open) }}</span>
      </div>
      <div class="tooltip-row">
        <span>高</span><span>{{ formatPrice(tooltipData?.high) }}</span>
      </div>
      <div class="tooltip-row">
        <span>低</span><span>{{ formatPrice(tooltipData?.low) }}</span>
      </div>
      <div class="tooltip-row">
        <span>收</span><span :class="tooltipChangeClass">{{ formatPrice(tooltipData?.close) }}</span>
      </div>
      <div class="tooltip-row">
        <span>涨跌</span><span :class="tooltipChangeClass">{{ formatPct(tooltipData?.changePct) }}</span>
      </div>
      <div class="tooltip-row">
        <span>成交量</span><span>{{ formatVolume(tooltipData?.volume) }}</span>
      </div>
      <div v-if="tooltipData?.amount != null" class="tooltip-row">
        <span>成交额</span><span>{{ formatAmount(tooltipData?.amount) }}</span>
      </div>
      <div v-if="tooltipData?.turnoverRate != null" class="tooltip-row">
        <span>换手率</span><span>{{ tooltipData?.turnoverRate.toFixed(2) }}%</span>
      </div>
      <div class="tooltip-divider"></div>
      <div class="tooltip-row">
        <span class="open-line">开盘价线</span><span class="open-line">{{ formatPrice(tooltipData?.openLine) }}</span>
      </div>
      <div class="tooltip-row">
        <span class="ma5">MA5</span><span class="ma5">{{ formatPrice(tooltipData?.ma5) }}</span>
      </div>
      <div class="tooltip-row">
        <span class="ma10">MA10</span><span class="ma10">{{ formatPrice(tooltipData?.ma10) }}</span>
      </div>
      <div class="tooltip-row">
        <span class="ma20">MA20</span><span class="ma20">{{ formatPrice(tooltipData?.ma20) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import type { CSSProperties } from 'vue'
import { createChart, CrosshairMode } from 'lightweight-charts'
import type { ISeriesApi, IChartApi, CandlestickData, HistogramData, LineData, MouseEventParams } from 'lightweight-charts'
import type { Bar } from '../api/client'

export interface ChartTooltipExtra {
  amount?: number
  change_pct?: number
  turnover_rate?: number
}

const props = defineProps<{
  bars: Bar[]
  currentIndex: number
  extraData?: Record<string, ChartTooltipExtra>
  displayStartIndex?: number
  displayEndIndex?: number
}>()

const chartContainer = ref<HTMLDivElement | null>(null)
let chart: IChartApi | null = null
let candleSeries: ISeriesApi<'Candlestick'> | null = null
let volumeSeries: ISeriesApi<'Histogram'> | null = null
let ma5Series: ISeriesApi<'Line'> | null = null
let ma10Series: ISeriesApi<'Line'> | null = null
let ma20Series: ISeriesApi<'Line'> | null = null
let openLineSeries: ISeriesApi<'Line'> | null = null

const tooltipVisible = ref(false)
const tooltipStyle = ref<CSSProperties>({ left: '0px', top: '0px' })
const tooltipData = ref<{
  time?: string
  open?: number
  high?: number
  low?: number
  close?: number
  changePct?: number
  volume?: number
  amount?: number
  turnoverRate?: number
  ma5?: number
  ma10?: number
  ma20?: number
  openLine?: number
} | null>(null)

const tooltipChangeClass = computed(() => {
  const pct = tooltipData.value?.changePct
  if (pct == null) return ''
  return pct > 0 ? 'up' : pct < 0 ? 'down' : ''
})

function formatPrice(price?: number | null) {
  if (price == null) return '-'
  return price.toFixed(2)
}

function formatPct(pct?: number | null) {
  if (pct == null) return '-'
  const sign = pct > 0 ? '+' : ''
  return `${sign}${pct.toFixed(2)}%`
}

function formatVolume(vol?: number | null) {
  if (vol == null) return '-'
  if (vol >= 1e8) return `${(vol / 1e8).toFixed(2)}亿`
  if (vol >= 1e4) return `${(vol / 1e4).toFixed(2)}万`
  return `${Math.round(vol)}`
}

function formatAmount(amount?: number | null) {
  if (amount == null) return '-'
  if (amount >= 1e8) return `${(amount / 1e8).toFixed(2)}亿`
  if (amount >= 1e4) return `${(amount / 1e4).toFixed(2)}万`
  return `${Math.round(amount)}`
}

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

function updateTooltip(param: MouseEventParams) {
  if (!param.point || !param.time || !candleSeries) {
    tooltipVisible.value = false
    return
  }

  const seriesData = param.seriesData.get(candleSeries)
  if (!seriesData) {
    tooltipVisible.value = false
    return
  }

  const candle = seriesData as CandlestickData
  const timeStr = candle.time as string
  const bar = props.bars.find((b) => b.timestamp.split('T')[0] === timeStr)
  if (!bar) {
    tooltipVisible.value = false
    return
  }

  const ma5Data = param.seriesData.get(ma5Series!) as LineData | undefined
  const ma10Data = param.seriesData.get(ma10Series!) as LineData | undefined
  const ma20Data = param.seriesData.get(ma20Series!) as LineData | undefined
  const openLineData = param.seriesData.get(openLineSeries!) as LineData | undefined

  const extra = props.extraData?.[timeStr]
  tooltipData.value = {
    time: timeStr,
    open: candle.open,
    high: candle.high,
    low: candle.low,
    close: candle.close,
    changePct: extra?.change_pct,
    volume: bar.volume,
    amount: extra?.amount,
    turnoverRate: extra?.turnover_rate,
    ma5: ma5Data?.value,
    ma10: ma10Data?.value,
    ma20: ma20Data?.value,
    openLine: openLineData?.value,
  }

  const containerRect = chartContainer.value?.getBoundingClientRect()
  if (containerRect) {
    const viewportX = containerRect.left + param.point.x
    const viewportY = containerRect.top + param.point.y
    let left = viewportX + 12
    let top = viewportY + 12
    // 防止 tooltip 超出视口右边界
    if (left + 150 > window.innerWidth) {
      left = viewportX - 158
    }
    // 防止 tooltip 超出视口下边界
    if (top + 260 > window.innerHeight) {
      top = viewportY - 270
    }
    tooltipStyle.value = {
      position: 'fixed',
      left: `${left}px`,
      top: `${top}px`,
    }
  }

  tooltipVisible.value = true
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
    crosshair: {
      mode: CrosshairMode.Magnet,
      vertLine: {
        color: 'rgba(117, 134, 150, 0.5)',
        labelBackgroundColor: '#758696',
        style: 2,
      },
      horzLine: {
        color: 'rgba(117, 134, 150, 0.5)',
        labelBackgroundColor: '#758696',
        style: 2,
      },
    },
    autoSize: true,
  })

  candleSeries = chart.addCandlestickSeries({
    upColor: '#ef4444',
    downColor: '#22c55e',
    borderUpColor: '#ef4444',
    borderDownColor: '#22c55e',
    wickUpColor: '#ef4444',
    wickDownColor: '#22c55e',
    priceLineVisible: false,
  })
  candleSeries.priceScale().applyOptions({
    scaleMargins: { top: 0.02, bottom: 0.28 },
  })

  volumeSeries = chart.addHistogramSeries({
    color: '#3b82f6',
    priceFormat: { type: 'volume' },
    priceScaleId: 'left',
    priceLineVisible: false,
  })
  volumeSeries.priceScale().applyOptions({
    scaleMargins: { top: 0.74, bottom: 0.02 },
  })
  // 隐藏左侧成交量坐标轴刻度与边框，只保留图形区域
  chart.priceScale('left').applyOptions({
    visible: false,
  })

  ma5Series = chart.addLineSeries({
    color: '#f59e0b',
    lineWidth: 2,
    priceLineVisible: false,
    lastValueVisible: false,
  })

  ma10Series = chart.addLineSeries({
    color: '#60a5fa',
    lineWidth: 2,
    priceLineVisible: false,
    lastValueVisible: false,
  })

  ma20Series = chart.addLineSeries({
    color: '#c084fc',
    lineWidth: 2,
    priceLineVisible: false,
    lastValueVisible: false,
  })

  openLineSeries = chart.addLineSeries({
    color: '#22d3ee',
    lineWidth: 1,
    priceLineVisible: false,
    lastValueVisible: false,
  })

  chart.subscribeCrosshairMove(updateTooltip)
  chart.timeScale().fitContent()
}

function updateChart() {
  if (!candleSeries || !volumeSeries || !ma5Series || !ma10Series || !ma20Series || !openLineSeries || !chart) return

  const total = props.bars.length
  const displayEnd = Math.min(props.displayEndIndex ?? total - 1, props.currentIndex, total - 1)
  const displayStart = Math.max(props.displayStartIndex ?? 0, 0)
  if (displayStart > displayEnd) {
    candleSeries.setData([])
    volumeSeries.setData([])
    ma5Series.setData([])
    ma10Series.setData([])
    ma20Series.setData([])
    openLineSeries.setData([])
    return
  }

  // MA 需要基于到 displayEnd 为止的全部数据计算，这样显示区域开头的 MA20 才有值
  const historyForMA = props.bars.slice(0, displayEnd + 1).map(toChartData)
  const displayBars = props.bars.slice(displayStart, displayEnd + 1)
  const candleData = displayBars.map(toChartData)
  const firstDisplayTime = candleData[0]?.time as string
  const volumeData: HistogramData[] = displayBars.map((bar) => ({
    time: bar.timestamp.split('T')[0] as string,
    value: bar.volume,
    color: bar.close >= bar.open ? '#ef4444' : '#22c55e',
  }))
  const openLineData: LineData[] = displayBars.map((bar) => ({
    time: bar.timestamp.split('T')[0] as string,
    value: bar.open,
  }))

  const filterToDisplay = (data: LineData[]) =>
    firstDisplayTime ? data.filter((d) => (d.time as string) >= firstDisplayTime) : data

  candleSeries.setData(candleData)
  volumeSeries.setData(volumeData)
  ma5Series.setData(filterToDisplay(calculateMA(historyForMA, 5)))
  ma10Series.setData(filterToDisplay(calculateMA(historyForMA, 10)))
  ma20Series.setData(filterToDisplay(calculateMA(historyForMA, 20)))
  openLineSeries.setData(openLineData)

  // 当调用方明确指定了显示范围时，强制锁定可见区域，避免 fitContent
  // 把未传入 series 的历史空白也展示出来（表现为左侧无 K 线）。
  if (props.displayStartIndex !== undefined || props.displayEndIndex !== undefined) {
    chart.timeScale().setVisibleLogicalRange({ from: 0, to: Math.max(0, displayBars.length - 1) })
  } else {
    chart.timeScale().fitContent()
  }
}

onMounted(() => {
  initChart()
  updateChart()
})

onUnmounted(() => {
  chart?.remove()
})

watch(() => [props.bars, props.currentIndex, props.displayStartIndex, props.displayEndIndex], updateChart, { deep: true })
</script>

<style scoped>
.chart-panel {
  flex: 1;
  min-height: 0;
  border-radius: 4px;
  overflow: hidden;
  position: relative;
}

.custom-tooltip {
  position: fixed;
  z-index: 300;
  min-width: 140px;
  padding: 8px 10px;
  background: rgba(17, 24, 39, 0.95);
  border: 1px solid #374151;
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
  pointer-events: none;
  font-size: 12px;
  color: #e5e7eb;
}

.tooltip-date {
  font-weight: 600;
  margin-bottom: 6px;
  color: #fff;
  border-bottom: 1px solid #374151;
  padding-bottom: 4px;
}

.tooltip-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  line-height: 1.6;
}

.tooltip-row span:first-child {
  color: #9ca3af;
}

.tooltip-divider {
  height: 1px;
  background: #374151;
  margin: 6px 0;
}

.ma5 {
  color: #f59e0b;
}

.ma10 {
  color: #60a5fa;
}

.ma20 {
  color: #c084fc;
}

.open-line {
  color: #22d3ee;
}

.up {
  color: #ef4444;
}

.down {
  color: #22c55e;
}
</style>
