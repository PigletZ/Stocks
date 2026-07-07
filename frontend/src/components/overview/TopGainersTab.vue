<template>
  <div class="top-gainers-tab">
    <div class="tab-header">
      <h2>涨幅榜</h2>
      <div class="header-controls">
        <input type="date" v-model="selectedDate" @change="onDateChange" />
        <span v-if="effectiveDate && effectiveDate !== selectedDate" class="date-note">
          数据日期：{{ effectiveDate }}
        </span>
        <span v-if="loading" class="loading-text">加载中...</span>
      </div>
    </div>

    <div class="rankings-grid">
      <section class="ranking-panel">
        <h3>五日涨幅榜</h3>
        <div class="table-container">
          <table class="stock-table">
            <thead>
              <tr>
                <th>排名</th>
                <th>代码</th>
                <th>名称</th>
                <th>最新价</th>
                <th>区间涨幅</th>
                <th>成交额</th>
                <th>换手率</th>
                <th>所属行业</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in fiveDay" :key="`5-${item.code}`">
                <td>{{ item.rank }}</td>
                <td>{{ item.code }}</td>
                <td>{{ item.name }}</td>
                <td>{{ item.close.toFixed(2) }}</td>
                <td :class="{ up: item.gain > 0, down: item.gain < 0 }">
                  {{ item.gain > 0 ? '+' : '' }}{{ item.gain.toFixed(2) }}%
                </td>
                <td>{{ formatAmount(item.amount) }}</td>
                <td>{{ item.turnover_rate.toFixed(2) }}%</td>
                <td>{{ item.industry || '-' }}</td>
                <td class="actions">
                  <router-link :to="`/stock/${item.code}`" class="btn-link">复盘</router-link>
                  <button class="btn-link" @click="$emit('add-watchlist', item.code)">加自选</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="fiveDay.length === 0 && !loading" class="empty-panel">
          暂无五日涨幅榜数据
        </div>
      </section>

      <section class="ranking-panel">
        <h3>十日涨幅榜</h3>
        <div class="table-container">
          <table class="stock-table">
            <thead>
              <tr>
                <th>排名</th>
                <th>代码</th>
                <th>名称</th>
                <th>最新价</th>
                <th>区间涨幅</th>
                <th>成交额</th>
                <th>换手率</th>
                <th>所属行业</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in tenDay" :key="`10-${item.code}`">
                <td>{{ item.rank }}</td>
                <td>{{ item.code }}</td>
                <td>{{ item.name }}</td>
                <td>{{ item.close.toFixed(2) }}</td>
                <td :class="{ up: item.gain > 0, down: item.gain < 0 }">
                  {{ item.gain > 0 ? '+' : '' }}{{ item.gain.toFixed(2) }}%
                </td>
                <td>{{ formatAmount(item.amount) }}</td>
                <td>{{ item.turnover_rate.toFixed(2) }}%</td>
                <td>{{ item.industry || '-' }}</td>
                <td class="actions">
                  <router-link :to="`/stock/${item.code}`" class="btn-link">复盘</router-link>
                  <button class="btn-link" @click="$emit('add-watchlist', item.code)">加自选</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="tenDay.length === 0 && !loading" class="empty-panel">
          暂无十日涨幅榜数据
        </div>
      </section>

      <section class="ranking-panel">
        <h3>二十日涨幅榜</h3>
        <div class="table-container">
          <table class="stock-table">
            <thead>
              <tr>
                <th>排名</th>
                <th>代码</th>
                <th>名称</th>
                <th>最新价</th>
                <th>区间涨幅</th>
                <th>成交额</th>
                <th>换手率</th>
                <th>所属行业</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in twentyDay" :key="`20-${item.code}`">
                <td>{{ item.rank }}</td>
                <td>{{ item.code }}</td>
                <td>{{ item.name }}</td>
                <td>{{ item.close.toFixed(2) }}</td>
                <td :class="{ up: item.gain > 0, down: item.gain < 0 }">
                  {{ item.gain > 0 ? '+' : '' }}{{ item.gain.toFixed(2) }}%
                </td>
                <td>{{ formatAmount(item.amount) }}</td>
                <td>{{ item.turnover_rate.toFixed(2) }}%</td>
                <td>{{ item.industry || '-' }}</td>
                <td class="actions">
                  <router-link :to="`/stock/${item.code}`" class="btn-link">复盘</router-link>
                  <button class="btn-link" @click="$emit('add-watchlist', item.code)">加自选</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="twentyDay.length === 0 && !loading" class="empty-panel">
          暂无二十日涨幅榜数据
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { fetchTopGainers } from '../../api/client'
import type { TopGainerItem } from '../../api/client'

defineEmits<{
  'add-watchlist': [code: string]
}>()

const selectedDate = ref(new Date().toISOString().split('T')[0])
const effectiveDate = ref('')
const fiveDay = ref<TopGainerItem[]>([])
const tenDay = ref<TopGainerItem[]>([])
const twentyDay = ref<TopGainerItem[]>([])
const loading = ref(false)

async function loadData() {
  loading.value = true
  try {
    const res = await fetchTopGainers(selectedDate.value)
    effectiveDate.value = res.effective_date
    fiveDay.value = res.five_day
    tenDay.value = res.ten_day
    twentyDay.value = res.twenty_day
  } catch (err) {
    console.error('Failed to load top gainers', err)
  } finally {
    loading.value = false
  }
}

function onDateChange() {
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
.top-gainers-tab {
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
}

.ranking-panel {
  background: #111827;
  border-radius: 8px;
  padding: 16px;
  min-width: 0;
}

.ranking-panel h3 {
  font-size: 14px;
  font-weight: 600;
  color: #e5e7eb;
  margin: 0 0 12px 0;
}

.table-container {
  overflow-x: auto;
}

.stock-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.stock-table th,
.stock-table td {
  padding: 8px;
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
  padding: 24px 0;
  color: #6b7280;
  font-size: 14px;
}
</style>
