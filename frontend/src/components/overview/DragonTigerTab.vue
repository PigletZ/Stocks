<template>
  <div class="dragon-tiger-tab">
    <div class="tab-header">
      <h2>龙虎榜</h2>
      <div class="header-controls">
        <input type="date" v-model="selectedDate" @change="onDateChange" />
        <div class="sort-toggle">
          <button
            class="toggle-btn"
            :class="{ active: sortBy === 'net_amount' }"
            @click="setSort('net_amount')"
          >
            净买额 {{ sortBy === 'net_amount' ? (order === 'desc' ? '↓' : '↑') : '' }}
          </button>
          <button
            class="toggle-btn"
            :class="{ active: sortBy === 'change_pct' }"
            @click="setSort('change_pct')"
          >
            涨跌幅 {{ sortBy === 'change_pct' ? (order === 'desc' ? '↓' : '↑') : '' }}
          </button>
        </div>
        <span v-if="loading" class="loading-text">加载中...</span>
      </div>
    </div>

    <div v-if="items.length > 0" class="table-container">
      <table class="stock-table">
        <thead>
          <tr>
            <th>代码</th>
            <th>名称</th>
            <th>上榜日</th>
            <th>收盘价</th>
            <th>涨跌幅</th>
            <th>龙虎榜净买额</th>
            <th>上榜原因</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="`${item.代码}-${item.上榜原因}`">
            <td>{{ item.代码 }}</td>
            <td>{{ item.名称 }}</td>
            <td>{{ item.上榜日 }}</td>
            <td>{{ item.收盘价.toFixed(2) }}</td>
            <td :class="{ up: item.涨跌幅 > 0, down: item.涨跌幅 < 0 }">
              {{ item.涨跌幅 > 0 ? '+' : '' }}{{ item.涨跌幅.toFixed(2) }}%
            </td>
            <td :class="{ up: item.龙虎榜净买额 > 0, down: item.龙虎榜净买额 < 0 }">
              {{ formatAmount(item.龙虎榜净买额) }}
            </td>
            <td class="reason">{{ item.上榜原因 }}</td>
            <td class="actions">
              <router-link :to="`/stock/${item.代码}`" class="btn-link">复盘</router-link>
              <button class="btn-link" @click="$emit('add-watchlist', item.代码)">加自选</button>
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
      暂无龙虎榜数据
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { fetchDragonTiger } from '../../api/client'
import type { DragonTigerItem } from '../../api/client'

defineEmits<{
  'add-watchlist': [code: string]
}>()

type SortField = 'change_pct' | 'net_amount' | 'trade_date'

const items = ref<DragonTigerItem[]>([])
const total = ref(0)
const loading = ref(false)
const selectedDate = ref(new Date().toISOString().split('T')[0])
const sortBy = ref<SortField>('net_amount')
const order = ref<'asc' | 'desc'>('desc')
const page = ref(1)
const pageSize = ref(20)

const totalPages = computed(() => Math.ceil(total.value / pageSize.value))
const hasPrev = computed(() => page.value > 1)
const hasNext = computed(() => page.value < totalPages.value)

async function loadData() {
  loading.value = true
  try {
    const offset = (page.value - 1) * pageSize.value
    const res = await fetchDragonTiger(
      selectedDate.value,
      sortBy.value,
      order.value,
      offset,
      pageSize.value,
    )
    items.value = res.items
    total.value = res.total
  } catch (err) {
    console.error('Failed to load dragon-tiger list', err)
  } finally {
    loading.value = false
  }
}

function setSort(field: SortField) {
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
  const sign = amount < 0 ? '-' : ''
  const absAmount = Math.abs(amount)
  if (absAmount >= 1e12) {
    return sign + (absAmount / 1e12).toFixed(2) + '万亿'
  }
  if (absAmount >= 1e8) {
    return sign + (absAmount / 1e8).toFixed(2) + '亿'
  }
  if (absAmount >= 1e4) {
    return sign + (absAmount / 1e4).toFixed(2) + '万'
  }
  return sign + absAmount.toFixed(0)
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.dragon-tiger-tab {
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

.reason {
  white-space: normal;
  min-width: 200px;
  color: #d1d5db;
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
