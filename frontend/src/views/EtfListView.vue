<template>
  <div class="etf-list">
    <div class="header">
      <h1>全 ETF 列表</h1>
      <span v-if="effectiveDate" class="date-note">数据日期：{{ effectiveDate }}</span>
    </div>

    <div class="filters">
      <select v-model="category" @change="onCategoryChange">
        <option value="">全部品类</option>
        <option v-for="cat in categories" :key="cat" :value="cat">{{ cat }}</option>
      </select>
      <span class="count">共 {{ total }} 条</span>
    </div>

    <div class="table-container">
      <table class="stock-table">
        <thead>
          <tr>
            <th @click="setSort('code')">代码 {{ sortIndicator('code') }}</th>
            <th @click="setSort('name')">名称 {{ sortIndicator('name') }}</th>
            <th @click="setSort('category')">品类 {{ sortIndicator('category') }}</th>
            <th @click="setSort('close')">最新价 {{ sortIndicator('close') }}</th>
            <th @click="setSort('change_pct')">涨跌幅 {{ sortIndicator('change_pct') }}</th>
            <th @click="setSort('amount')">成交额 {{ sortIndicator('amount') }}</th>
            <th>基金管理</th>
            <th>基金类型</th>
            <th>跟踪标的</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="etf in etfs" :key="etf.code">
            <td>{{ etf.code }}</td>
            <td>{{ etf.name }}</td>
            <td><span class="category-tag">{{ etf.category || '-' }}</span></td>
            <td>{{ etf.close != null ? etf.close.toFixed(3) : '-' }}</td>
            <td :class="{ up: (etf.change_pct || 0) > 0, down: (etf.change_pct || 0) < 0 }">
              {{ formatChange(etf.change_pct) }}
            </td>
            <td>{{ etf.amount != null ? formatAmount(etf.amount) : '-' }}</td>
            <td>{{ etf.management || '-' }}</td>
            <td>{{ etf.fund_type || '-' }}</td>
            <td :title="etf.benchmark" class="benchmark">{{ etf.benchmark || '-' }}</td>
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
import { fetchEtfList, fetchEtfCategories } from '../api/client'
import type { EtfItem } from '../api/client'

const etfs = ref<EtfItem[]>([])
const total = ref(0)
const effectiveDate = ref('')
const categories = ref<string[]>([])
const category = ref('')
const page = ref(1)
const pageSize = ref(50)
const sortBy = ref('change_pct')
const sortOrder = ref<'asc' | 'desc'>('desc')

const totalPages = computed(() => Math.ceil(total.value / pageSize.value))

async function loadEtfs() {
  try {
    const offset = (page.value - 1) * pageSize.value
    const res = await fetchEtfList(
      sortBy.value,
      sortOrder.value,
      offset,
      pageSize.value,
      category.value,
    )
    etfs.value = res.items
    total.value = res.total
    effectiveDate.value = res.effective_date
  } catch (err) {
    console.error('Failed to load ETF list', err)
  }
}

async function loadCategories() {
  try {
    categories.value = await fetchEtfCategories()
  } catch (err) {
    console.error('Failed to load ETF categories', err)
  }
}

function onCategoryChange() {
  page.value = 1
  loadEtfs()
}

function setSort(field: string) {
  if (sortBy.value === field) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortBy.value = field
    sortOrder.value = 'desc'
  }
  page.value = 1
  loadEtfs()
}

function sortIndicator(field: string) {
  if (sortBy.value !== field) return ''
  return sortOrder.value === 'asc' ? '↑' : '↓'
}

function prevPage() {
  if (page.value > 1) {
    page.value--
    loadEtfs()
  }
}

function nextPage() {
  if (page.value < totalPages.value) {
    page.value++
    loadEtfs()
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
  loadCategories()
  loadEtfs()
})
</script>

<style scoped>
.etf-list {
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

.date-note {
  font-size: 13px;
  color: #9ca3af;
}

.filters {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
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

.stock-table td.benchmark {
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.category-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  background: #1f2937;
  color: #9ca3af;
  font-size: 12px;
  border: 1px solid #374151;
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
