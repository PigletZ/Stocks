<template>
  <div class="stock-list">
    <div class="header">
      <h1>全市场股票</h1>
      <div class="header-actions">
        <button class="btn-secondary" @click="syncQuotes" :disabled="syncingQuotes">
          {{ syncingQuotes ? '同步行情中...' : '同步行情' }}
        </button>
        <button class="btn-secondary" @click="syncStocks" :disabled="syncingStocks">
          {{ syncingStocks ? '同步中...' : '同步股票列表' }}
        </button>
      </div>
    </div>

    <div class="filters">
      <input
        v-model="search"
        placeholder="输入股票代码或名称搜索"
        @input="debouncedSearch"
      />
      <select v-model="industry" @change="loadStocks">
        <option value="">全部行业</option>
        <option v-for="ind in industries" :key="ind" :value="ind">{{ ind }}</option>
      </select>
      <span class="count">共 {{ total }} 条</span>
    </div>

    <div class="table-container">
      <table class="stock-table">
        <thead>
          <tr>
            <th @click="setSort('code')">代码 {{ sortIndicator('code') }}</th>
            <th @click="setSort('name')">名称 {{ sortIndicator('name') }}</th>
            <th @click="setSort('close')">最新价 {{ sortIndicator('close') }}</th>
            <th @click="setSort('change_pct')">涨跌幅 {{ sortIndicator('change_pct') }}</th>
            <th @click="setSort('amount')">成交额 {{ sortIndicator('amount') }}</th>
            <th @click="setSort('turnover_rate')">换手率 {{ sortIndicator('turnover_rate') }}</th>
            <th @click="setSort('float_mv')">流通市值 {{ sortIndicator('float_mv') }}</th>
            <th @click="setSort('total_mv')">总市值 {{ sortIndicator('total_mv') }}</th>
            <th @click="setSort('pe')">PE {{ sortIndicator('pe') }}</th>
            <th @click="setSort('pb')">PB {{ sortIndicator('pb') }}</th>
            <th>行业</th>
            <th @click="setSort('list_date')">上市日期 {{ sortIndicator('list_date') }}</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="stock in stocks" :key="stock.code">
            <td>{{ stock.code }}</td>
            <td>{{ stock.name }}</td>
            <td>{{ stock.close != null ? stock.close.toFixed(2) : '-' }}</td>
            <td :class="{ up: (stock.change_pct || 0) > 0, down: (stock.change_pct || 0) < 0 }">
              {{ formatChange(stock.change_pct) }}
            </td>
            <td>{{ stock.amount != null ? formatAmount(stock.amount) : '-' }}</td>
            <td>{{ stock.turnover_rate != null ? stock.turnover_rate.toFixed(2) + '%' : '-' }}</td>
            <td>{{ stock.float_mv != null ? formatAmount(stock.float_mv) : '-' }}</td>
            <td>{{ stock.total_mv != null ? formatAmount(stock.total_mv) : '-' }}</td>
            <td>{{ stock.pe != null ? stock.pe.toFixed(2) : '-' }}</td>
            <td>{{ stock.pb != null ? stock.pb.toFixed(2) : '-' }}</td>
            <td>{{ stock.industry || '-' }}</td>
            <td>{{ stock.list_date || '-' }}</td>
            <td class="actions">
              <router-link :to="`/stock/${stock.code}`" class="btn-link">复盘</router-link>
              <button class="btn-link" @click="addToWl(stock.code)">加自选</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="totalPages > 1" class="pagination">
      <button class="nav-btn" :disabled="page <= 1" @click="prevPage">上一页</button>
      <span class="page-info">第 {{ page }} / {{ totalPages }} 页</span>
      <button class="nav-btn" :disabled="page >= totalPages" @click="nextPage">下一页</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import {
  fetchStockList,
  fetchIndustries,
  syncStockList,
  syncDailyQuotes,
  addToWatchlist,
} from '../api/client'
import type { StockListItem } from '../api/client'

const search = ref('')
const industry = ref('')
const industries = ref<string[]>([])
const stocks = ref<StockListItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const sortBy = ref('code')
const sortOrder = ref<'asc' | 'desc'>('asc')
const syncingStocks = ref(false)
const syncingQuotes = ref(false)
let debounceTimer: ReturnType<typeof setTimeout> | null = null

const totalPages = computed(() => Math.ceil(total.value / pageSize.value))

async function loadStocks() {
  try {
    const res = await fetchStockList(
      search.value || undefined,
      industry.value || undefined,
      page.value,
      pageSize.value,
      sortBy.value,
      sortOrder.value,
    )
    stocks.value = res.items
    total.value = res.total
  } catch (err) {
    console.error('Failed to load stocks', err)
  }
}

async function loadIndustries() {
  try {
    industries.value = await fetchIndustries()
  } catch (err) {
    console.error('Failed to load industries', err)
  }
}

function debouncedSearch() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    page.value = 1
    loadStocks()
  }, 300)
}

function setSort(field: string) {
  if (sortBy.value === field) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortBy.value = field
    sortOrder.value = 'asc'
  }
  page.value = 1
  loadStocks()
}

function sortIndicator(field: string) {
  if (sortBy.value !== field) return ''
  return sortOrder.value === 'asc' ? '↑' : '↓'
}

function prevPage() {
  if (page.value > 1) {
    page.value--
    loadStocks()
  }
}

function nextPage() {
  if (page.value < totalPages.value) {
    page.value++
    loadStocks()
  }
}

async function syncStocks() {
  syncingStocks.value = true
  try {
    await syncStockList()
    await loadIndustries()
    await loadStocks()
  } catch (err: any) {
    alert(err?.response?.data?.detail || '同步股票列表失败')
  } finally {
    syncingStocks.value = false
  }
}

async function syncQuotes() {
  syncingQuotes.value = true
  try {
    await syncDailyQuotes()
    await loadStocks()
  } catch (err: any) {
    alert(err?.response?.data?.detail || '同步行情失败')
  } finally {
    syncingQuotes.value = false
  }
}

async function addToWl(code: string) {
  try {
    await addToWatchlist(code)
    alert(`已添加 ${code} 到自选`)
  } catch (err: any) {
    alert(err?.response?.data?.detail || '添加失败')
  }
}

function formatChange(value?: number): string {
  if (value == null) return '-'
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

onMounted(() => {
  loadIndustries()
  loadStocks()
})
</script>

<style scoped>
.stock-list {
  padding: 24px;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header h1 {
  font-size: 20px;
  font-weight: 600;
}

.header-actions {
  display: flex;
  gap: 10px;
}

.filters {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.filters input,
.filters select {
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid #374151;
  background: #1f2937;
  color: #fff;
  font-size: 13px;
}

.filters input {
  flex: 1;
  max-width: 300px;
}

.count {
  font-size: 13px;
  color: #9ca3af;
}

.table-container {
  flex: 1;
  overflow-y: auto;
  border: 1px solid #1f2937;
  border-radius: 8px;
}

.stock-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.stock-table th,
.stock-table td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid #1f2937;
  white-space: nowrap;
}

.stock-table th {
  background: #111827;
  color: #9ca3af;
  font-weight: 500;
  position: sticky;
  top: 0;
  cursor: pointer;
  user-select: none;
}

.stock-table th:hover {
  color: #e5e7eb;
}

.stock-table tr:hover {
  background: #1f2937;
}

.stock-table td.up {
  color: #ef4444;
}

.stock-table td.down {
  color: #22c55e;
}

.actions {
  display: flex;
  gap: 10px;
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

.btn-secondary {
  padding: 8px 14px;
  border-radius: 6px;
  border: 1px solid #374151;
  background: #1f2937;
  color: #fff;
  cursor: pointer;
  font-size: 13px;
}

.btn-secondary:hover:not(:disabled) {
  background: #374151;
}

.btn-secondary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 16px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #1f2937;
}

.nav-btn {
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid #374151;
  background: #1f2937;
  color: #fff;
  cursor: pointer;
  font-size: 13px;
}

.nav-btn:hover:not(:disabled) {
  background: #374151;
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
