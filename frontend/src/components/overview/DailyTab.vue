<template>
  <div class="daily-tab">
    <!-- 日期选择器 -->
    <section class="date-bar">
      <div class="date-info">
        <span v-if="!isToday" class="date-note">查看历史数据</span>
        <span v-if="loading" class="loading-text">加载中...</span>
      </div>
      <div class="date-controls">
        <button class="nav-btn" @click="prevDay" title="上一日">◀</button>
        <input
          type="date"
          :value="selectedDate"
          class="date-input"
          @change="onDateInputChange"
        />
        <button class="nav-btn" @click="nextDay" title="下一日">▶</button>
        <button class="today-btn" @click="goToday">今天</button>
        <button
          class="sync-btn"
          :disabled="syncing"
          @click="syncToday"
          title="重新拉取当前日期的指数与市场统计数据"
        >
          {{ syncing ? '同步中...' : '同步数据' }}
        </button>
      </div>
    </section>

    <!-- 主要指数 -->
    <section class="indices-section">
      <div class="section-title">
        <h2>主要指数</h2>
      </div>
      <div v-if="indices.length > 0" class="indices-grid">
        <div
          v-for="index in indices"
          :key="index.code"
          class="index-card"
          :class="{ up: index.change_pct >= 0, down: index.change_pct < 0 }"
          @mouseenter="hoveredIndexCode = index.code"
          @mouseleave="hoveredIndexCode = ''"
        >
          <div class="index-name">{{ index.name }}</div>
          <div class="index-price">{{ index.price.toFixed(2) }}</div>
          <div class="index-change">
            <span>{{ index.change >= 0 ? '+' : '' }}{{ index.change.toFixed(2) }}</span>
            <span>{{ index.change_pct >= 0 ? '+' : '' }}{{ index.change_pct.toFixed(2) }}%</span>
          </div>
          <IndexChartPopup
            v-if="hoveredIndexCode === index.code"
            :code="index.code"
            :name="index.name"
            class="index-chart-popup"
          />
        </div>
      </div>
      <div v-else class="empty-panel">暂无指数数据</div>
    </section>

    <!-- 市场统计 + 趋势图 -->
    <section class="stats-chart-row">
      <!-- 市场统计 -->
      <div class="stats-section">
        <div class="section-title">
          <h2>市场统计</h2>
          <span v-if="!isToday" class="history-note">历史日期仅展示涨跌停/炸板数</span>
        </div>
        <div class="stats-grid">
          <div class="stat-card up-down">
            <div class="stat-label">涨跌家数</div>
            <div class="stat-value">
              <span class="up-count">{{ marketSummary.up }}</span>
              <span class="separator">|</span>
              <span class="down-count">{{ marketSummary.down }}</span>
            </div>
          </div>
          <template v-if="isToday">
            <div class="stat-card flat">
              <div class="stat-label">平盘家数</div>
              <div class="stat-value">{{ marketSummary.flat }}</div>
            </div>
            <div class="stat-card total">
              <div class="stat-label">总家数</div>
              <div class="stat-value">{{ marketSummary.total }}</div>
            </div>
          </template>
          <div class="stat-card turnover">
            <div class="stat-label">总成交额</div>
            <div class="stat-value">{{ formatAmount(marketSummary.total_turnover) }}</div>
          </div>
          <div class="stat-card limit-up">
            <div class="stat-label">涨停</div>
            <div class="stat-value">{{ marketSummary.limit_up }}</div>
          </div>
          <div class="stat-card limit-down">
            <div class="stat-label">跌停</div>
            <div class="stat-value">{{ marketSummary.limit_down }}</div>
          </div>
          <div class="stat-card opened-limit">
            <div class="stat-label">炸板</div>
            <div class="stat-value">{{ marketSummary.opened_limit }}</div>
          </div>
        </div>
      </div>

      <!-- 市场情绪趋势图 -->
      <div class="chart-section">
        <div class="chart-header">
          <h2>市场情绪趋势</h2>
          <div class="chart-controls">
            <button
              v-for="range in quickRanges"
              :key="range.label"
              class="range-btn"
              :class="{ active: activeRange === range.label }"
              @click="setQuickRange(range)"
            >
              {{ range.label }}
            </button>
            <input type="date" v-model="chartStart" />
            <span class="range-separator">至</span>
            <input type="date" v-model="chartEnd" />
            <button class="btn-primary" @click="loadMarketHistory">生成</button>
          </div>
        </div>
        <div ref="historyChart" class="history-chart"></div>
        <div v-if="historyNote" class="history-note">{{ historyNote }}</div>
      </div>
    </section>

    <!-- 板块排行 -->
    <section class="sector-ranking-section">
      <div class="section-title">
        <h2>板块排行</h2>
        <span v-if="sectorLoading" class="loading-text">加载中...</span>
      </div>
      <div class="sector-grid">
        <section class="panel">
          <div class="panel-header">
            <h2>行业板块涨幅</h2>
            <div class="sort-toggle">
              <button
                class="toggle-btn"
                :class="{ active: industrySortBy === 'change_pct' }"
                @click="industrySortBy = 'change_pct'"
              >
                涨跌幅
              </button>
              <button
                class="toggle-btn"
                :class="{ active: industrySortBy === 'volume' }"
                @click="industrySortBy = 'volume'"
              >
                成交量
              </button>
            </div>
          </div>
          <div v-if="industrySectors.length > 0" class="stock-list">
            <div
              v-for="sector in industrySectors"
              :key="sector.sector_code"
              class="stock-item"
            >
              <div class="stock-main">
                <span class="stock-code">{{ sector.sector_name }}</span>
              </div>
              <div class="stock-extra">
                <span class="stock-change" :class="{ up: sector.change_pct > 0, down: sector.change_pct < 0 }">
                  {{ sector.change_pct > 0 ? '+' : '' }}{{ sector.change_pct.toFixed(2) }}%
                </span>
                <span class="stock-total">{{ formatAmount(sector.volume) }}</span>
              </div>
            </div>
          </div>
          <div v-else-if="!sectorLoading" class="empty">暂无行业板块数据</div>
        </section>

        <section class="panel">
          <div class="panel-header">
            <h2>概念板块涨幅</h2>
            <div class="sort-toggle">
              <button
                class="toggle-btn"
                :class="{ active: conceptSortBy === 'change_pct' }"
                @click="conceptSortBy = 'change_pct'"
              >
                涨跌幅
              </button>
              <button
                class="toggle-btn"
                :class="{ active: conceptSortBy === 'volume' }"
                @click="conceptSortBy = 'volume'"
              >
                成交量
              </button>
            </div>
          </div>
          <div v-if="conceptSectors.length > 0" class="stock-list">
            <div
              v-for="sector in conceptSectors"
              :key="sector.sector_code"
              class="stock-item"
            >
              <div class="stock-main">
                <span class="stock-code">{{ sector.sector_name }}</span>
              </div>
              <div class="stock-extra">
                <span class="stock-change" :class="{ up: sector.change_pct > 0, down: sector.change_pct < 0 }">
                  {{ sector.change_pct > 0 ? '+' : '' }}{{ sector.change_pct.toFixed(2) }}%
                </span>
                <span class="stock-total">{{ formatAmount(sector.volume) }}</span>
              </div>
            </div>
          </div>
          <div v-else-if="!sectorLoading" class="empty">暂无概念板块数据</div>
        </section>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import * as echarts from 'echarts'
import IndexChartPopup from '../IndexChartPopup.vue'
import { fetchMarketHistory, fetchTradeDates, syncDailyOverview, fetchSectorRankingDaily } from '../../api/client'
import type {
  MarketHistoryItem,
  SectorDailyItem,
  SectorRankingDaily,
  MarketSummary,
  IndexSpot,
} from '../../api/client'

const props = defineProps<{
  marketSummary: MarketSummary
  indices: IndexSpot[]
  selectedDate: string
  loading?: boolean
}>()

const emit = defineEmits<{
  'update:selectedDate': [date: string]
  refresh: []
}>()

const isToday = computed(() => props.selectedDate === formatDate(new Date()))

function formatDate(d: Date): string {
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const tradeDates = ref<Set<string>>(new Set())
const hoveredIndexCode = ref('')

// 交易日加载后，若当前日期不是交易日，自动回退到最近的前一个交易日
watch(tradeDates, (dates) => {
  if (dates.size === 0 || !props.selectedDate) return
  if (!dates.has(props.selectedDate)) {
    const prev = findNearestTradeDate(props.selectedDate, 'prev')
    if (prev && prev !== props.selectedDate) {
      emit('update:selectedDate', prev)
    }
  }
})

async function loadTradeDates() {
  try {
    const end = formatDate(new Date())
    const start = formatDate(new Date(Date.now() - 90 * 24 * 60 * 60 * 1000))
    const dates = await fetchTradeDates(start, end)
    tradeDates.value = new Set(dates)
  } catch (err) {
    console.error('Failed to load trade dates', err)
  }
}

function findNearestTradeDate(target: string, direction: 'prev' | 'next'): string | null {
  if (tradeDates.value.size === 0) return null
  const sorted = Array.from(tradeDates.value).sort()
  if (direction === 'prev') {
    for (let i = sorted.length - 1; i >= 0; i--) {
      if (sorted[i] < target) return sorted[i]
    }
  } else {
    for (let i = 0; i < sorted.length; i++) {
      if (sorted[i] > target) return sorted[i]
    }
  }
  return null
}

function snapToTradeDate(target: string): string {
  if (tradeDates.value.has(target)) return target
  if (tradeDates.value.size === 0) return target
  const sorted = Array.from(tradeDates.value).sort()
  // 找最近的交易日
  let nearest = sorted[0]
  let minDiff = Infinity
  const targetTime = new Date(target).getTime()
  for (const d of sorted) {
    const diff = Math.abs(new Date(d).getTime() - targetTime)
    if (diff < minDiff) {
      minDiff = diff
      nearest = d
    }
  }
  return nearest
}

function prevDay() {
  const prev = findNearestTradeDate(props.selectedDate, 'prev')
  if (prev) emit('update:selectedDate', prev)
}

function nextDay() {
  const next = findNearestTradeDate(props.selectedDate, 'next')
  if (next) emit('update:selectedDate', next)
}

function goToday() {
  const today = formatDate(new Date())
  emit('update:selectedDate', snapToTradeDate(today))
}

function onDateInputChange(e: Event) {
  const target = e.target as HTMLInputElement
  emit('update:selectedDate', snapToTradeDate(target.value))
}

const historyChart = ref<HTMLDivElement | null>(null)
let chartInstance: echarts.ECharts | null = null

const syncing = ref(false)

const sectorRanking = ref<SectorRankingDaily>({
  industry: [],
  concept: [],
})
const sectorLoading = ref(false)
const industrySortBy = ref<'change_pct' | 'volume'>('change_pct')
const conceptSortBy = ref<'change_pct' | 'volume'>('change_pct')

const chartStart = ref(formatDate(new Date(Date.now() - 6 * 24 * 60 * 60 * 1000)))
const chartEnd = ref(formatDate(new Date()))
const activeRange = ref('近一周')
const marketHistory = ref<MarketHistoryItem[]>([])
const historyNote = ref('')

const quickRanges = [
  { label: '近一周', days: 6 },
  { label: '近一月', days: 29 },
  { label: '近三月', days: 89 },
]

function setQuickRange(range: { label: string; days: number }) {
  activeRange.value = range.label
  const end = new Date()
  const start = new Date(Date.now() - range.days * 24 * 60 * 60 * 1000)
  chartEnd.value = formatDate(end)
  chartStart.value = formatDate(start)
  loadMarketHistory()
}

function initHistoryChart() {
  if (!historyChart.value) return
  chartInstance = echarts.init(historyChart.value)
}

function updateHistoryChart() {
  if (!chartInstance || marketHistory.value.length === 0) return

  const dates = marketHistory.value.map((item) => item.date)
  const hasUpDown = marketHistory.value.some((item) => item.up > 0 || item.down > 0)

  const series: echarts.SeriesOption[] = [
    {
      name: '涨停',
      type: 'line',
      data: marketHistory.value.map((item) => item.limit_up),
      smooth: true,
      itemStyle: { color: '#f97316' },
      areaStyle: { opacity: 0.1 },
    },
    {
      name: '跌停',
      type: 'line',
      data: marketHistory.value.map((item) => item.limit_down),
      smooth: true,
      itemStyle: { color: '#3b82f6' },
      areaStyle: { opacity: 0.1 },
    },
    {
      name: '炸板',
      type: 'line',
      data: marketHistory.value.map((item) => item.opened_limit),
      smooth: true,
      itemStyle: { color: '#a855f7' },
      areaStyle: { opacity: 0.1 },
    },
  ]

  if (hasUpDown) {
    series.unshift(
      {
        name: '上涨家数',
        type: 'line',
        data: marketHistory.value.map((item) => item.up),
        smooth: true,
        itemStyle: { color: '#ef4444' },
      },
      {
        name: '下跌家数',
        type: 'line',
        data: marketHistory.value.map((item) => item.down),
        smooth: true,
        itemStyle: { color: '#22c55e' },
      }
    )
    historyNote.value = ''
  } else {
    historyNote.value = '提示：历史日期的上涨/下跌家数需要额外计算，当前折线图展示涨停、跌停、炸板数据。'
  }

  chartInstance.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
    },
    legend: {
      data: series.map((s) => s.name as string),
      textStyle: { color: '#9ca3af' },
      bottom: 0,
    },
    grid: {
      left: 50,
      right: 20,
      top: 20,
      bottom: 40,
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisLine: { lineStyle: { color: '#374151' } },
      axisLabel: { color: '#9ca3af' },
    },
    yAxis: {
      type: 'value',
      axisLine: { lineStyle: { color: '#374151' } },
      axisLabel: { color: '#9ca3af' },
      splitLine: { lineStyle: { color: '#374151' } },
    },
    series,
  })
}

async function loadMarketHistory() {
  try {
    const data = await fetchMarketHistory(chartStart.value, chartEnd.value)
    marketHistory.value = data
    updateHistoryChart()
  } catch (err) {
    console.error('Failed to load market history', err)
  }
}

async function syncToday() {
  if (syncing.value) return
  syncing.value = true
  try {
    await syncDailyOverview(props.selectedDate)
    emit('refresh')
  } catch (err: any) {
    console.error('Failed to sync daily overview', err)
  } finally {
    syncing.value = false
  }
}

async function loadSectorRanking() {
  sectorLoading.value = true
  try {
    sectorRanking.value = await fetchSectorRankingDaily(props.selectedDate, 'all', 'change_pct', 50)
  } catch (err: any) {
    console.error('Failed to load sector ranking', err)
  } finally {
    sectorLoading.value = false
  }
}

function sortSectors(list: SectorDailyItem[], sortBy: 'change_pct' | 'volume'): SectorDailyItem[] {
  return [...list].sort((a, b) => b[sortBy] - a[sortBy])
}

const industrySectors = computed(() =>
  sortSectors(sectorRanking.value.industry, industrySortBy.value)
)
const conceptSectors = computed(() =>
  sortSectors(sectorRanking.value.concept, conceptSortBy.value)
)

function handleResize() {
  chartInstance?.resize()
}

onMounted(() => {
  initHistoryChart()
  loadMarketHistory()
  loadTradeDates()
  loadSectorRanking()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  chartInstance?.dispose()
})

watch(
  () => [chartStart.value, chartEnd.value],
  () => {
    activeRange.value = '自定义'
  }
)

watch(
  () => props.selectedDate,
  () => {
    loadSectorRanking()
  }
)

function formatAmount(amount: number): string {
  const absAmount = Math.abs(amount)
  if (absAmount >= 1e12) {
    return (absAmount / 1e12).toFixed(2) + '万亿'
  }
  if (absAmount >= 1e8) {
    return (absAmount / 1e8).toFixed(2) + '亿'
  }
  if (absAmount >= 1e4) {
    return (absAmount / 1e4).toFixed(2) + '万'
  }
  return absAmount.toFixed(0)
}
</script>

<style scoped>
.daily-tab {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.date-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  background: #1f2937;
  border-radius: 10px;
  padding: 14px 18px;
}

.date-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.date-controls {
  display: flex;
  align-items: center;
  gap: 10px;
}

.nav-btn,
.today-btn,
.sync-btn {
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid #374151;
  background: #111827;
  color: #e5e7eb;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.nav-btn:hover,
.today-btn:hover,
.sync-btn:hover {
  background: #1f2937;
}

.sync-btn {
  background: #1e3a8a;
  border-color: #1e40af;
  color: #bfdbfe;
}

.sync-btn:hover {
  background: #1e40af;
  color: #fff;
}

.sync-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.date-input {
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px solid #374151;
  background: #111827;
  color: #e5e7eb;
  font-size: 14px;
}

.date-note {
  font-size: 13px;
  color: #6b7280;
}

.loading-text {
  font-size: 13px;
  color: #6b7280;
}

.indices-section {
  margin-bottom: 0;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}

.section-title h2 {
  font-size: 16px;
  font-weight: 600;
  color: #e5e7eb;
  margin: 0;
}

.history-note {
  font-size: 12px;
  color: #6b7280;
}

.empty-panel {
  background: #1f2937;
  border-radius: 10px;
  padding: 30px;
  text-align: center;
  color: #6b7280;
  font-size: 14px;
}

.indices-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 14px;
}

.index-card {
  position: relative;
  background: #1f2937;
  border-radius: 10px;
  padding: 18px;
}

.index-chart-popup {
  position: absolute;
  top: 0;
  left: calc(100% + 12px);
  z-index: 100;
}

.index-card.up {
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.index-card.down {
  border: 1px solid rgba(34, 197, 94, 0.3);
}

.index-name {
  font-size: 14px;
  color: #9ca3af;
  margin-bottom: 8px;
}

.index-price {
  font-size: 24px;
  font-weight: 700;
  color: #fff;
  margin-bottom: 8px;
}

.index-change {
  display: flex;
  gap: 12px;
  font-size: 14px;
}

.index-card.up .index-change {
  color: #ef4444;
}

.index-card.down .index-change {
  color: #22c55e;
}

.stats-chart-row {
  display: grid;
  grid-template-columns: minmax(320px, 420px) 1fr;
  gap: 20px;
}

.stats-section {
  background: #1f2937;
  border-radius: 10px;
  padding: 20px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 14px;
}

.stat-card {
  background: #111827;
  border-radius: 10px;
  padding: 16px;
  border-left: 4px solid #374151;
}

.stat-card.up {
  border-left-color: #ef4444;
}

.stat-card.down {
  border-left-color: #22c55e;
}

.stat-card.flat {
  border-left-color: #6b7280;
}

.stat-card.limit-up {
  border-left-color: #f97316;
}

.stat-card.limit-down {
  border-left-color: #3b82f6;
}

.stat-card.opened-limit {
  border-left-color: #a855f7;
}

.stat-card.total {
  border-left-color: #6b7280;
}

.stat-card.up-down {
  border-left-color: #ef4444;
}

.stat-card.up-down .stat-value {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stat-card.up-down .up-count {
  color: #ef4444;
}

.stat-card.up-down .down-count {
  color: #22c55e;
}

.stat-card.up-down .separator {
  color: #6b7280;
  font-weight: 400;
}

.stat-card.turnover {
  border-left-color: #f59e0b;
}

.stat-label {
  font-size: 13px;
  color: #9ca3af;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #fff;
}

.chart-section {
  background: #1f2937;
  border-radius: 10px;
  padding: 20px;
  min-width: 0;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;
}

.chart-header h2 {
  font-size: 16px;
  font-weight: 600;
  color: #e5e7eb;
  margin: 0;
}

.chart-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.range-btn {
  padding: 5px 12px;
  border-radius: 4px;
  border: 1px solid #374151;
  background: transparent;
  color: #9ca3af;
  font-size: 13px;
  cursor: pointer;
}

.range-btn.active,
.range-btn:hover {
  background: #2563eb;
  border-color: #2563eb;
  color: #fff;
}

.chart-controls input[type='date'] {
  padding: 5px 8px;
  font-size: 13px;
}

.range-separator {
  color: #9ca3af;
  font-size: 13px;
}

.btn-primary {
  padding: 5px 14px;
  border-radius: 4px;
  border: 1px solid #2563eb;
  background: #2563eb;
  color: #fff;
  font-size: 13px;
  cursor: pointer;
}

.btn-primary:hover {
  background: #1d4ed8;
}

.history-chart {
  width: 100%;
  height: 280px;
}

.history-note {
  margin-top: 10px;
  font-size: 12px;
  color: #6b7280;
}

.sector-ranking-section {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.sector-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  gap: 20px;
}

.sort-toggle {
  display: flex;
  gap: 6px;
}

.toggle-btn {
  padding: 5px 12px;
  border-radius: 4px;
  border: 1px solid #374151;
  background: #111827;
  color: #9ca3af;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.toggle-btn:hover {
  background: #1f2937;
  color: #e5e7eb;
}

.toggle-btn.active {
  background: #2563eb;
  border-color: #2563eb;
  color: #fff;
}

.panel {
  background: #1f2937;
  border-radius: 10px;
  padding: 18px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}

.panel-header h2 {
  font-size: 16px;
  font-weight: 600;
  color: #e5e7eb;
  margin: 0;
}

.panel-more {
  font-size: 13px;
  color: #60a5fa;
  text-decoration: none;
}

.stock-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stock-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-radius: 6px;
  background: #111827;
  text-decoration: none;
  transition: background 0.2s;
}

.stock-item:hover {
  background: #1a2230;
}

.stock-main {
  display: flex;
  gap: 10px;
  align-items: center;
}

.stock-code {
  font-weight: 600;
  color: #fff;
  font-size: 14px;
  min-width: 70px;
}

.stock-name {
  color: #9ca3af;
  font-size: 13px;
}

.stock-meta {
  font-size: 12px;
  color: #6b7280;
  background: #1f2937;
  padding: 2px 8px;
  border-radius: 4px;
}

.empty {
  color: #6b7280;
  font-size: 13px;
  text-align: center;
  padding: 30px 0;
}

.empty a {
  color: #60a5fa;
  text-decoration: none;
}

@media (max-width: 1200px) {
  .index-chart-popup {
    top: calc(100% + 12px);
    left: 0;
  }
}

@media (max-width: 900px) {
  .stats-chart-row {
    grid-template-columns: 1fr;
  }
}
</style>
