<template>
  <Teleport to="body">
    <div v-if="visible" class="modal-overlay" @click.self="$emit('close')">
      <div class="stock-detail-popup">
        <div class="popup-header">
          <div class="popup-title">
            <span class="stock-name">{{ name }}</span>
            <span class="stock-code">{{ code }}</span>
            <span v-if="industry" class="industry-tag">{{ industry }}</span>
          </div>
          <button class="close-btn" @click="$emit('close')">×</button>
        </div>

        <div class="popup-body">
          <div v-if="loading" class="status-text">加载中...</div>
          <div v-else-if="error" class="status-text error">{{ error }}</div>

          <template v-else>
            <div class="chart-section">
              <ChartPanel
                v-if="bars.length > 0"
                :bars="bars"
                :current-index="bars.length - 1"
                :display-start-index="chartDisplayRange.start"
                :display-end-index="chartDisplayRange.end"
                :extra-data="chartExtraData"
              />
              <div v-else class="empty">暂无 K 线数据</div>
            </div>
          </template>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, computed } from 'vue'
import ChartPanel from '../ChartPanel.vue'
import { fetchBars, fetchStockDailyHistory } from '../../api/client'
import type { Bar, StockDailyHistoryItem } from '../../api/client'
import type { ChartTooltipExtra } from '../ChartPanel.vue'

const props = defineProps<{
  visible: boolean
  code: string
  name: string
  industry?: string
}>()

defineEmits<{
  (e: 'close'): void
}>()

const bars = ref<Bar[]>([])
const allDailyHistory = ref<StockDailyHistoryItem[]>([])
const loading = ref(false)
const error = ref('')

const chartExtraData = computed(() => {
  const map: Record<string, ChartTooltipExtra> = {}
  for (const row of allDailyHistory.value) {
    map[row.trade_date] = {
      amount: row.amount,
      change_pct: row.change_pct,
      turnover_rate: row.turnover_rate,
    }
  }
  return map
})

const chartDisplayRange = computed(() => {
  const total = bars.value.length
  if (total === 0) return { start: 0, end: -1 }
  const displayCount = 30
  const end = total - 1
  const start = Math.max(0, total - displayCount)
  return { start, end }
})

function computeDateRange() {
  const end = new Date()
  // 为了计算 MA20，需要多取约 60 个交易日的历史数据
  const fetchStart = new Date(Date.now() - 90 * 24 * 60 * 60 * 1000)
  const fmt = (d: Date) => {
    const year = d.getFullYear()
    const month = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    return `${year}-${month}-${day}`
  }
  return { fetchStart: fmt(fetchStart), end: fmt(end) }
}

async function loadData() {
  if (!props.code) return
  loading.value = true
  error.value = ''
  bars.value = []
  allDailyHistory.value = []
  try {
    const { fetchStart, end } = computeDateRange()
    const [barsData, historyData] = await Promise.all([
      fetchBars(props.code, '1d', fetchStart, end),
      fetchStockDailyHistory(props.code, fetchStart, end),
    ])
    bars.value = barsData
    allDailyHistory.value = historyData
  } catch (err: any) {
    error.value = '加载失败，请稍后重试'
    console.error('Failed to load stock detail', err)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  if (props.visible) loadData()
})

watch(() => [props.visible, props.code], ([visible]) => {
  if (visible) {
    loadData()
  }
})
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
  padding: 20px;
}

.stock-detail-popup {
  width: 900px;
  max-width: 95vw;
  max-height: 90vh;
  background: #111827;
  border: 1px solid #374151;
  border-radius: 12px;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.5);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.popup-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 18px;
  border-bottom: 1px solid #374151;
  background: #0b0f19;
}

.popup-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.stock-name {
  font-size: 16px;
  font-weight: 600;
  color: #fff;
}

.stock-code {
  font-size: 13px;
  color: #9ca3af;
}

.industry-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(59, 130, 246, 0.15);
  color: #60a5fa;
  font-size: 12px;
}

.close-btn {
  background: transparent;
  border: none;
  color: #9ca3af;
  font-size: 22px;
  cursor: pointer;
  line-height: 1;
}

.close-btn:hover {
  color: #fff;
}

.popup-body {
  flex: 1;
  min-height: 0;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow: hidden;
}

.chart-section {
  height: 520px;
  min-height: 400px;
  display: flex;
  flex-direction: column;
}

.up {
  color: #ef4444;
}

.down {
  color: #22c55e;
}

.status-text {
  text-align: center;
  color: #9ca3af;
  padding: 40px;
}

.status-text.error {
  color: #ef4444;
}

.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #6b7280;
  font-size: 14px;
}
</style>
