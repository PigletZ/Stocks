<template>
  <div class="overview-page">
    <div v-if="globalError" class="global-error">
      {{ globalError }}
      <button class="close-btn" @click="globalError = ''">×</button>
    </div>

    <div class="overview">
      <header class="page-header">
        <h1>概览</h1>
        <div class="last-update">{{ updateTimeText }}</div>
      </header>

      <!-- 标签导航 -->
      <nav class="tab-nav">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="tab-btn"
          :class="{ active: activeTab === tab.key }"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
        </button>
      </nav>

      <!-- 标签内容 -->
      <div class="tab-content">
        <DailyTab
          v-if="activeTab === 'daily'"
          :market-summary="dailyOverview.market_stats"
          :indices="dailyOverview.indices"
          :selected-date="selectedDate"
          :loading="loadingDaily"
          @update:selected-date="onDateChange"
          @refresh="loadDailyOverview"
        />

        <LimitTab
          v-if="activeTab === 'limit-up'"
          title="涨停股票"
          type="up"
          @add-watchlist="addToWl"
        />

        <LimitTab
          v-if="activeTab === 'limit-down'"
          title="跌停股票"
          type="down"
          @add-watchlist="addToWl"
        />

        <DragonTigerTab
          v-if="activeTab === 'dragon-tiger'"
          @add-watchlist="addToWl"
        />

        <TopGainersTab
          v-if="activeTab === 'top-gainers'"
          @add-watchlist="addToWl"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import DailyTab from '../components/overview/DailyTab.vue'
import LimitTab from '../components/overview/LimitTab.vue'
import DragonTigerTab from '../components/overview/DragonTigerTab.vue'
import TopGainersTab from '../components/overview/TopGainersTab.vue'
import {
  fetchDailyOverview,
  fetchTradeDates,
  addToWatchlist,
} from '../api/client'
import type {
  DailyOverview,
} from '../api/client'

const activeTab = ref('daily')
const globalError = ref('')
const lastUpdateTime = ref(new Date())

const updateTimeText = computed(() => {
  return `数据更新于：${formatDate(lastUpdateTime.value)}`
})

const formatDate = (d: Date) => {
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function getLastTradingDate(): Date {
  const d = new Date()
  const day = d.getDay()
  if (day === 0) {
    d.setDate(d.getDate() - 2)
  } else if (day === 6) {
    d.setDate(d.getDate() - 1)
  }
  return d
}

const tabs = [
  { key: 'daily', label: '日概览' },
  { key: 'limit-up', label: '涨停' },
  { key: 'limit-down', label: '跌停' },
  { key: 'dragon-tiger', label: '龙虎榜' },
  { key: 'top-gainers', label: '涨幅榜' },
]

// 日概览
const selectedDate = ref('')
const dailyOverview = ref<DailyOverview>({
  date: selectedDate.value,
  indices: [],
  market_stats: {
    up: 0,
    down: 0,
    flat: 0,
    total: 0,
    limit_up: 0,
    limit_down: 0,
    opened_limit: 0,
    total_turnover: 0,
  },
})
const loadingDaily = ref(false)

async function loadDailyOverview() {
  loadingDaily.value = true
  try {
    dailyOverview.value = await fetchDailyOverview(selectedDate.value)
  } catch (err: any) {
    globalError.value = err?.response?.data?.detail || err.message || '加载日概览失败'
    console.error('Failed to load daily overview', err)
  } finally {
    loadingDaily.value = false
  }
}

function onDateChange(date: string) {
  selectedDate.value = date
  loadDailyOverview()
}

watch(activeTab, (tab) => {
  if (tab === 'daily' && selectedDate.value) {
    loadDailyOverview()
  }
})

watch(selectedDate, (newDate) => {
  if (activeTab.value === 'daily' && newDate) {
    loadDailyOverview()
  }
})

async function initSelectedDate() {
  try {
    const end = formatDate(new Date())
    const start = formatDate(new Date(Date.now() - 90 * 24 * 60 * 60 * 1000))
    const dates = await fetchTradeDates(start, end)
    if (dates.length > 0) {
      // 取最近的交易日
      const lastTradeDate = dates.sort().pop()!
      selectedDate.value = lastTradeDate
      return
    }
  } catch (err) {
    console.error('Failed to load trade dates', err)
  }
  // fallback：周末修正
  selectedDate.value = formatDate(getLastTradingDate())
}

async function addToWl(code: string) {
  try {
    await addToWatchlist(code)
    alert(`已添加 ${code} 到自选`)
  } catch (err: any) {
    alert(err?.response?.data?.detail || '添加失败')
  }
}

onMounted(() => {
  initSelectedDate()
})
</script>

<style scoped>
.overview-page {
  position: relative;
}

.global-error {
  position: fixed;
  top: 16px;
  right: 16px;
  z-index: 1000;
  background: #7f1d1d;
  color: #fecaca;
  padding: 12px 40px 12px 16px;
  border-radius: 8px;
  max-width: 400px;
  font-size: 13px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.close-btn {
  position: absolute;
  top: 6px;
  right: 10px;
  background: transparent;
  border: none;
  color: #fecaca;
  font-size: 18px;
  cursor: pointer;
  padding: 0;
  line-height: 1;
}

.overview {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-header h1 {
  font-size: 24px;
  font-weight: 600;
  color: #fff;
}

.last-update {
  font-size: 13px;
  color: #6b7280;
}

.tab-nav {
  display: flex;
  gap: 8px;
  margin-bottom: 24px;
  border-bottom: 1px solid #1f2937;
  padding-bottom: 12px;
}

.tab-btn {
  padding: 8px 18px;
  border-radius: 6px;
  border: 1px solid transparent;
  background: transparent;
  color: #9ca3af;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.tab-btn:hover {
  background: #1f2937;
  color: #e5e7eb;
}

.tab-btn.active {
  background: #2563eb;
  color: #fff;
  border-color: #2563eb;
}

.tab-content {
  min-height: 400px;
}
</style>
