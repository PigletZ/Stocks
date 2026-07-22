<template>
  <div class="etf-gainers">
    <div class="header">
      <h1>ETF 涨幅榜</h1>
      <div class="header-controls">
        <select v-model="category" @change="onCategoryChange">
          <option value="">全部品类</option>
          <option v-for="cat in categories" :key="cat" :value="cat">{{ cat }}</option>
        </select>
        <input type="date" v-model="selectedDate" @change="onDateChange" />
        <span v-if="effectiveDate && effectiveDate !== selectedDate" class="date-note">
          数据日期：{{ effectiveDate }}
        </span>
        <span v-if="loading" class="loading-text">加载中...</span>
      </div>
    </div>

    <div class="rankings-grid">
      <section v-for="section in sections" :key="section.key" class="ranking-panel">
        <h3>
          {{ section.title }}
          <span v-if="section.note" class="panel-note">{{ section.note }}</span>
        </h3>
        <div class="table-container">
          <table class="stock-table">
            <thead>
              <tr>
                <th>排名</th>
                <th>代码</th>
                <th>名称</th>
                <th>最新价</th>
                <th>区间涨幅</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in section.items" :key="`${section.key}-${item.code}`">
                <td>{{ item.rank }}</td>
                <td>{{ item.code }}</td>
                <td :title="item.name" class="name-cell">{{ item.name }}</td>
                <td>{{ item.close.toFixed(3) }}</td>
                <td :class="{ up: item.gain > 0, down: item.gain < 0 }">
                  {{ item.gain > 0 ? '+' : '' }}{{ item.gain.toFixed(2) }}%
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="section.items.length === 0 && !loading" class="empty-panel">
          暂无{{ section.title }}数据
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { fetchEtfGainers, fetchEtfCategories } from '../api/client'
import type { EtfGainersResponse } from '../api/client'

const selectedDate = ref(new Date().toISOString().split('T')[0])
const category = ref('')
const categories = ref<string[]>([])
const effectiveDate = ref('')
const response = ref<EtfGainersResponse | null>(null)
const loading = ref(false)

const sections = computed(() => [
  { key: '2', title: '两日涨幅榜', note: '已过滤成交额 < 1000 万', items: response.value?.two_day || [] },
  { key: '5', title: '五日涨幅榜', note: '', items: response.value?.five_day || [] },
  { key: '10', title: '十日涨幅榜', note: '', items: response.value?.ten_day || [] },
  { key: '20', title: '二十日涨幅榜', note: '', items: response.value?.twenty_day || [] },
])

async function loadData() {
  loading.value = true
  try {
    const res = await fetchEtfGainers(selectedDate.value, category.value)
    effectiveDate.value = res.effective_date
    response.value = res
  } catch (err) {
    console.error('Failed to load ETF gainers', err)
  } finally {
    loading.value = false
  }
}

async function loadCategories() {
  try {
    categories.value = await fetchEtfCategories()
  } catch (err) {
    console.error('Failed to load ETF categories', err)
  }
}

function onDateChange() {
  loadData()
}

function onCategoryChange() {
  loadData()
}

onMounted(() => {
  loadCategories()
  loadData()
})
</script>

<style scoped>
.etf-gainers {
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
  flex-wrap: wrap;
  gap: 12px;
}

.header h1 {
  font-size: 20px;
  font-weight: 600;
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

.date-note {
  font-size: 13px;
  color: #f59e0b;
}

.loading-text {
  font-size: 13px;
  color: #6b7280;
}

.rankings-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 20px;
  flex: 1;
  overflow-y: auto;
}

.ranking-panel {
  background: #1f2937;
  border-radius: 8px;
  padding: 16px;
}

.ranking-panel h3 {
  font-size: 14px;
  font-weight: 600;
  color: #e5e7eb;
  margin: 0 0 12px 0;
}

.panel-note {
  font-size: 12px;
  font-weight: 400;
  color: #6b7280;
  margin-left: 8px;
}

.table-container {
  overflow-x: auto;
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

.stock-table td.name-cell {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.empty-panel {
  text-align: center;
  padding: 24px 0;
  color: #6b7280;
  font-size: 14px;
}
</style>
