<template>
  <div class="limit-tab">
    <div class="tab-header">
      <h2>{{ title }}</h2>
      <div class="header-controls">
        <input type="date" v-model="selectedDate" @change="onDateChange" />
        <div class="sort-toggle">
          <button
            class="toggle-btn"
            :class="{ active: sortBy === 'pct_chg' }"
            @click="setSort('pct_chg')"
          >
            涨跌幅 {{ sortBy === 'pct_chg' ? (order === 'desc' ? '↓' : '↑') : '' }}
          </button>
          <button
            class="toggle-btn"
            :class="{ active: sortBy === 'amount' }"
            @click="setSort('amount')"
          >
            成交额 {{ sortBy === 'amount' ? (order === 'desc' ? '↓' : '↑') : '' }}
          </button>
          <button
            class="toggle-btn"
            :class="{ active: sortBy === 'fd_ratio' }"
            @click="setSort('fd_ratio')"
          >
            封单比 {{ sortBy === 'fd_ratio' ? (order === 'desc' ? '↓' : '↑') : '' }}
          </button>
          <button
            class="toggle-btn"
            :class="{ active: sortBy === 'turnover_ratio' }"
            @click="setSort('turnover_ratio')"
          >
            换手率 {{ sortBy === 'turnover_ratio' ? (order === 'desc' ? '↓' : '↑') : '' }}
          </button>
          <button
            class="toggle-btn"
            :class="{ active: sortBy === 'first_time' }"
            @click="setSort('first_time')"
          >
            首封时间 {{ sortBy === 'first_time' ? (order === 'desc' ? '↓' : '↑') : '' }}
          </button>
          <button
            class="toggle-btn"
            :class="{ active: sortBy === 'limit_times' }"
            @click="setSort('limit_times')"
          >
            几天几板 {{ sortBy === 'limit_times' ? (order === 'desc' ? '↓' : '↑') : '' }}
          </button>
        </div>
        <span v-if="loading" class="loading-text">加载中...</span>
      </div>
    </div>

    <div v-if="stocks.length > 0" class="table-container">
      <table class="stock-table">
        <thead>
          <tr>
            <th>代码</th>
            <th>名称</th>
            <th>最新价</th>
            <th>涨跌幅</th>
            <th>成交额</th>
            <th>封单比</th>
            <th>换手率</th>
            <th>流通值</th>
            <th>总市值</th>
            <th>首封时间</th>
            <th>封住时间</th>
            <th>开板次数</th>
            <th>{{ analysisLabel }}</th>
            <th>几天几板</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="stock in stocks" :key="stock.代码">
            <td>{{ stock.代码 }}</td>
            <td>{{ stock.名称 }}</td>
            <td>{{ stock.最新价.toFixed(2) }}</td>
            <td :class="{ up: stock.涨跌幅 > 0, down: stock.涨跌幅 < 0 }">
              {{ stock.涨跌幅 > 0 ? '+' : '' }}{{ stock.涨跌幅.toFixed(2) }}%
            </td>
            <td>{{ formatAmount(stock.成交额) }}</td>
            <td>{{ (stock.封单比 * 100).toFixed(2) }}%</td>
            <td>{{ stock.换手率.toFixed(2) }}%</td>
            <td>{{ formatAmount(stock.流通值) }}</td>
            <td>{{ formatAmount(stock.总市值) }}</td>
            <td>{{ formatTime(stock.首封时间) }}</td>
            <td>{{ formatTime(stock.封住时间) }}</td>
            <td>{{ stock.开板次数 }}</td>
            <td>{{ stock.涨停分析 || stock.跌停分析 || '-' }}</td>
            <td>{{ stock.几天几板 }}</td>
            <td class="actions">
              <router-link :to="`/stock/${stock.代码}`" class="btn-link">复盘</router-link>
              <button class="btn-link" @click="$emit('add-watchlist', stock.代码)">加自选</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="total > 0" class="pagination">
      <button class="nav-btn" :disabled="!hasPrev" @click="prevPage">上一页</button>
      <span class="page-info">第 {{ page }} / {{ totalPages }} 页，共 {{ total }} 条</span>
      <button class="nav-btn" :disabled="!hasNext" @click="nextPage">下一页</button>
    </div>
    <div v-else-if="!loading" class="empty-panel">
      暂无{{ title }}数据
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import {
  fetchLimitUpStocks,
  fetchLimitDownStocks,
  fetchOpenedLimitStocks,
} from '../../api/client'
import type { LimitStock } from '../../api/client'

const props = defineProps<{
  title: string
  type: 'up' | 'down' | 'opened'
}>()

defineEmits<{
  'add-watchlist': [code: string]
}>()

const stocks = ref<LimitStock[]>([])
const total = ref(0)
const loading = ref(false)
const selectedDate = ref(new Date().toISOString().split('T')[0])
const sortBy = ref('pct_chg')
const order = ref<'asc' | 'desc'>('desc')
const page = ref(1)
const pageSize = ref(20)

const totalPages = computed(() => Math.ceil(total.value / pageSize.value))
const hasPrev = computed(() => page.value > 1)
const hasNext = computed(() => page.value < totalPages.value)

const analysisLabel = computed(() => {
  if (props.type === 'down') return '跌停分析'
  return '涨停分析'
})

const fetchMap = {
  up: fetchLimitUpStocks,
  down: fetchLimitDownStocks,
  opened: fetchOpenedLimitStocks,
}

async function loadData() {
  loading.value = true
  try {
    const offset = (page.value - 1) * pageSize.value
    const res = await fetchMap[props.type](
      selectedDate.value,
      sortBy.value,
      order.value,
      offset,
      pageSize.value,
    )
    stocks.value = res.items
    total.value = res.total
  } catch (err) {
    console.error('Failed to load limit stocks', err)
  } finally {
    loading.value = false
  }
}

function setSort(field: string) {
  if (sortBy.value === field) {
    order.value = order.value === 'desc' ? 'asc' : 'desc'
  } else {
    sortBy.value = field
    order.value = 'desc'
  }
  page.value = 1
  loadData()
}

function prevPage() {
  if (hasPrev.value) {
    page.value--
    loadData()
  }
}

function nextPage() {
  if (hasNext.value) {
    page.value++
    loadData()
  }
}

function onDateChange() {
  page.value = 1
  loadData()
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

function formatTime(time: string | null): string {
  if (!time || time === 'None') return '-'
  const s = String(time).trim()
  if (s.length === 6) {
    return `${s.slice(0, 2)}:${s.slice(2, 4)}:${s.slice(4, 6)}`
  }
  if (s.length === 5) {
    return `${s.slice(0, 1)}:${s.slice(1, 3)}:${s.slice(3, 5)}`
  }
  return s
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.limit-tab {
  background: #1f2937;
  border-radius: 10px;
  padding: 20px;
}

.tab-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;
}

.tab-header h2 {
  font-size: 16px;
  font-weight: 600;
  color: #e5e7eb;
  margin: 0;
}

.header-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-controls input[type='date'] {
  padding: 5px 8px;
  font-size: 13px;
}

.loading-text {
  font-size: 13px;
  color: #6b7280;
}

.table-container {
  overflow-x: auto;
}

.stock-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.stock-table th,
.stock-table td {
  padding: 12px 16px;
  text-align: left;
  border-bottom: 1px solid #374151;
  white-space: nowrap;
}

.stock-table th {
  background: #111827;
  color: #9ca3af;
  font-weight: 500;
  position: sticky;
  top: 0;
}

.stock-table tr:hover {
  background: #374151;
}

.stock-table td.up {
  color: #ef4444;
}

.stock-table td.down {
  color: #22c55e;
}

.actions {
  display: flex;
  gap: 12px;
}

.btn-link {
  background: transparent;
  border: none;
  color: #60a5fa;
  cursor: pointer;
  font-size: 13px;
  text-decoration: none;
  padding: 0;
}

.btn-link:hover {
  color: #93c5fd;
}

.empty-panel {
  text-align: center;
  padding: 40px 0;
  color: #6b7280;
  font-size: 14px;
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

.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 16px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #374151;
}

.nav-btn {
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid #374151;
  background: #111827;
  color: #e5e7eb;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.nav-btn:hover:not(:disabled) {
  background: #1f2937;
}

.nav-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.page-info {
  font-size: 13px;
  color: #9ca3af;
}
</style>
