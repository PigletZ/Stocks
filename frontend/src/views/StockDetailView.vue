<template>
  <div class="stock-detail">
    <div class="detail-header">
      <div class="title">
        <h1>{{ code }}</h1>
        <span v-if="stock.name" class="stock-name">{{ stock.name }}</span>
        <span v-if="stock.change_pct != null" class="change-pct" :class="{ up: stock.change_pct > 0, down: stock.change_pct < 0 }">
          {{ stock.close?.toFixed(2) }} {{ formatChange(stock.change_pct) }}
        </span>
      </div>
      <div class="controls">
        <input type="date" v-model="startDate" />
        <input type="date" v-model="endDate" />
        <button class="btn-primary" @click="loadBars" :disabled="loading">
          {{ loading ? '加载中...' : '加载' }}
        </button>
        <button class="btn-secondary" @click="forceSync" :disabled="loading">同步</button>
      </div>
    </div>

    <div v-if="error" class="error">{{ error }}</div>

    <div class="info-panel" v-if="stock.code">
      <div class="info-item">
        <span class="label">行业</span>
        <span class="value">{{ stock.industry || '-' }}</span>
      </div>
      <div class="info-item">
        <span class="label">交易所</span>
        <span class="value">{{ stock.exchange }}</span>
      </div>
      <div class="info-item">
        <span class="label">上市日期</span>
        <span class="value">{{ stock.list_date || '-' }}</span>
      </div>
      <div class="info-item">
        <span class="label">成交额</span>
        <span class="value">{{ stock.amount != null ? formatAmount(stock.amount) : '-' }}</span>
      </div>
      <div class="info-item">
        <span class="label">换手率</span>
        <span class="value">{{ stock.turnover_rate != null ? stock.turnover_rate.toFixed(2) + '%' : '-' }}</span>
      </div>
      <div class="info-item">
        <span class="label">总市值</span>
        <span class="value">{{ stock.total_mv != null ? formatAmount(stock.total_mv) : '-' }}</span>
      </div>
      <div class="info-item">
        <span class="label">PE</span>
        <span class="value">{{ stock.pe != null ? stock.pe.toFixed(2) : '-' }}</span>
      </div>
      <div class="info-item">
        <span class="label">PB</span>
        <span class="value">{{ stock.pb != null ? stock.pb.toFixed(2) : '-' }}</span>
      </div>
    </div>

    <div class="detail-body">
      <aside class="replay-panel">
        <h3>回放控制</h3>
        <div class="replay-buttons">
          <button @click="togglePlay">{{ isPlaying ? '暂停' : '播放' }}</button>
          <button @click="stepBack">←</button>
          <button @click="stepForward">→</button>
        </div>
        <div class="speed-control">
          <label>速度: {{ speed }}x</label>
          <input type="range" min="1" max="16" step="1" v-model.number="speed" />
        </div>

        <div v-if="currentBar" class="current-bar">
          <h4>当前 K 线</h4>
          <div class="info-row"><span>日期: {{ currentBar.timestamp.split('T')[0] }}</span></div>
          <div class="info-row"><span>开盘: {{ currentBar.open.toFixed(2) }}</span></div>
          <div class="info-row"><span>收盘: {{ currentBar.close.toFixed(2) }}</span></div>
          <div class="info-row"><span>最高: {{ currentBar.high.toFixed(2) }}</span></div>
          <div class="info-row"><span>最低: {{ currentBar.low.toFixed(2) }}</span></div>
          <div class="info-row"><span>成交量: {{ currentBar.volume.toFixed(0) }}</span></div>
        </div>
      </aside>

      <section class="chart-wrapper">
        <ChartPanel :bars="bars" :current-index="currentIndex" />
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import ChartPanel from '../components/ChartPanel.vue'
import { fetchBars, syncBars, fetchStock, recordRecentView } from '../api/client'
import { useReplayStore } from '../stores/replay'
import type { Bar, StockListItem } from '../api/client'

const route = useRoute()
const store = useReplayStore()

const code = computed(() => route.params.code as string)
const stock = ref<StockListItem>({} as StockListItem)

const today = new Date()
const oneYearAgo = new Date(today.getFullYear() - 1, today.getMonth(), today.getDate())
const endDate = ref(today.toISOString().split('T')[0])
const startDate = ref(oneYearAgo.toISOString().split('T')[0])

const bars = ref<Bar[]>([])
const currentIndex = ref(0)
const isPlaying = ref(false)
const speed = ref(4)
const loading = ref(false)
const error = ref('')
const timer = ref<ReturnType<typeof setInterval> | null>(null)

const currentBar = computed(() => {
  if (currentIndex.value < 0 || currentIndex.value >= bars.value.length) return null
  return bars.value[currentIndex.value]
})

async function loadStockInfo() {
  try {
    stock.value = await fetchStock(code.value)
  } catch {
    stock.value = { code: code.value, name: '' } as StockListItem
  }
}

async function loadBars() {
  loading.value = true
  error.value = ''
  try {
    const data = await fetchBars(code.value, '1d', startDate.value, endDate.value)
    bars.value = data
    store.setBars(data)
    currentIndex.value = data.length > 0 ? data.length - 1 : 0
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function forceSync() {
  loading.value = true
  error.value = ''
  try {
    await syncBars(code.value, '1d', startDate.value, endDate.value)
    await loadBars()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err.message || '同步失败'
  } finally {
    loading.value = false
  }
}

function togglePlay() {
  if (isPlaying.value) pause()
  else play()
}

function play() {
  if (bars.value.length === 0) return
  if (currentIndex.value >= bars.value.length - 1) currentIndex.value = 0
  isPlaying.value = true
  timer.value = setInterval(() => {
    if (currentIndex.value < bars.value.length - 1) currentIndex.value++
    else pause()
  }, 1000 / speed.value)
}

function pause() {
  isPlaying.value = false
  if (timer.value) {
    clearInterval(timer.value)
    timer.value = null
  }
}

function stepForward() {
  pause()
  if (currentIndex.value < bars.value.length - 1) currentIndex.value++
}

function stepBack() {
  pause()
  if (currentIndex.value > 0) currentIndex.value--
}

function formatChange(value?: number): string {
  if (value == null) return ''
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}%`
}

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

watch(speed, () => {
  if (isPlaying.value) {
    pause()
    play()
  }
})

watch(code, () => {
  loadStockInfo()
  loadBars()
})

onMounted(() => {
  loadStockInfo()
  loadBars()
  recordRecentView(code.value).catch((err) => {
    console.error('Failed to record recent view', err)
  })
})
</script>

<style scoped>
.stock-detail {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow-y: auto;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  border-bottom: 1px solid #1f2937;
  gap: 16px;
  flex-wrap: wrap;
}

.title {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}

.title h1 {
  font-size: 20px;
  font-weight: 600;
}

.stock-name {
  font-size: 14px;
  color: #9ca3af;
}

.change-pct {
  font-size: 14px;
  font-weight: 500;
}

.change-pct.up {
  color: #ef4444;
}

.change-pct.down {
  color: #22c55e;
}

.controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.controls input,
.controls select {
  padding: 6px 10px;
  border-radius: 4px;
  border: 1px solid #374151;
  background: #1f2937;
  color: #fff;
  font-size: 13px;
}

.info-panel {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  padding: 12px 24px;
  border-bottom: 1px solid #1f2937;
  background: #111827;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 80px;
}

.info-item .label {
  font-size: 11px;
  color: #6b7280;
}

.info-item .value {
  font-size: 13px;
  color: #e5e7eb;
}

.detail-body {
  display: flex;
  flex: 1;
  min-height: 0;
  padding: 16px;
  gap: 16px;
}

.replay-panel {
  width: 240px;
  flex-shrink: 0;
  background: #1f2937;
  border-radius: 8px;
  padding: 16px;
  overflow-y: auto;
}

.replay-panel h3 {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 16px;
}

.replay-buttons {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.speed-control {
  margin-bottom: 20px;
}

.speed-control label {
  display: block;
  font-size: 13px;
  color: #9ca3af;
  margin-bottom: 6px;
}

.current-bar h4 {
  font-size: 13px;
  color: #9ca3af;
  margin-bottom: 10px;
}

.info-row {
  margin-top: 8px;
  font-size: 13px;
  color: #94a3b8;
}

.chart-wrapper {
  flex: 1;
  min-width: 0;
  background: #1f2937;
  border-radius: 8px;
  padding: 12px;
  display: flex;
  flex-direction: column;
}

.error {
  background: #7f1d1d;
  color: #fecaca;
  padding: 10px 24px;
  margin: 0;
}

.btn-primary,
.btn-secondary {
  padding: 6px 12px;
  border-radius: 4px;
  border: 1px solid #374151;
  background: #2563eb;
  color: #fff;
  cursor: pointer;
  font-size: 13px;
}

.btn-secondary {
  background: #1f2937;
}

button:hover:not(:disabled) {
  opacity: 0.9;
}

button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
