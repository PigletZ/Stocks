<template>
  <div class="watchlist">
    <div class="header">
      <h1>自选股票</h1>
      <button class="btn-secondary" @click="createGroup">新建分组</button>
    </div>

    <div v-for="group in groups" :key="group.id" class="group">
      <div class="group-title">
        <span>{{ group.name }}（{{ group.stocks.length }}）</span>
        <div class="group-actions">
          <button class="btn-link" @click="renameGroup(group.id)">重命名</button>
          <button class="btn-link danger" @click="deleteGroup(group.id)">删除</button>
        </div>
      </div>
      <div class="group-items">
        <div v-for="item in group.stocks" :key="item.code" class="stock-card">
          <div class="stock-info">
            <div class="stock-name">{{ item.name }} <span class="stock-code">{{ item.code }}</span></div>
            <div class="stock-meta">
              {{ item.exchange }} · {{ item.industry || '无行业' }}
            </div>
            <div v-if="item.close != null" class="stock-quote">
              <span :class="{ up: (item.change_pct || 0) > 0, down: (item.change_pct || 0) < 0 }">
                {{ item.close.toFixed(2) }} {{ formatChange(item.change_pct) }}
              </span>
              <span v-if="item.turnover_rate != null" class="turnover">换手 {{ item.turnover_rate.toFixed(2) }}%</span>
            </div>
          </div>
          <div class="stock-actions">
            <router-link :to="`/stock/${item.code}`" class="btn-link">复盘</router-link>
            <button class="btn-link" @click="moveGroup(item.code)">移动</button>
            <button class="btn-link danger" @click="remove(item.code)">删除</button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="groups.length === 0" class="empty">
      暂无自选股，请从<router-link to="/stocks">全市场股票</router-link>中添加
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  fetchWatchlistGroups,
  createWatchlistGroup,
  renameWatchlistGroup,
  deleteWatchlistGroup,
  removeFromWatchlist,
  moveWatchlistGroup,
} from '../api/client'
import type { WatchlistGroup } from '../api/client'

const groups = ref<WatchlistGroup[]>([])

async function load() {
  try {
    groups.value = await fetchWatchlistGroups()
  } catch (err) {
    console.error('Failed to load watchlist', err)
  }
}

async function createGroup() {
  const name = prompt('请输入新分组名称：')
  if (!name) return
  try {
    await createWatchlistGroup(name)
    await load()
  } catch (err: any) {
    alert(err?.response?.data?.detail || '创建失败')
  }
}

async function renameGroup(id: number) {
  const name = prompt('请输入新的分组名称：')
  if (!name) return
  try {
    await renameWatchlistGroup(id, name)
    await load()
  } catch (err: any) {
    alert(err?.response?.data?.detail || '重命名失败')
  }
}

async function deleteGroup(id: number) {
  const group = groups.value.find((g) => g.id === id)
  if (!group) return
  if (!confirm(`确定删除分组「${group.name}」？组内股票将移至默认分组。`)) return
  try {
    await deleteWatchlistGroup(id)
    await load()
  } catch (err: any) {
    alert(err?.response?.data?.detail || '删除失败')
  }
}

async function remove(code: string) {
  if (!confirm(`确定从自选删除 ${code}？`)) return
  try {
    await removeFromWatchlist(code)
    await load()
  } catch (err: any) {
    alert(err?.response?.data?.detail || '删除失败')
  }
}

async function moveGroup(code: string) {
  const options = groups.value
    .map((g, idx) => `${idx + 1}. ${g.name}`)
    .join('\n')
  const input = prompt(`请选择目标分组（输入序号）：\n${options}`)
  if (!input) return
  const idx = parseInt(input, 10) - 1
  if (idx < 0 || idx >= groups.value.length) {
    alert('无效的选择')
    return
  }
  try {
    await moveWatchlistGroup(code, groups.value[idx].id)
    await load()
  } catch (err: any) {
    alert(err?.response?.data?.detail || '移动失败')
  }
}

function formatChange(value?: number): string {
  if (value == null) return ''
  const sign = value > 0 ? '+' : ''
  return `（${sign}${value.toFixed(2)}%）`
}

onMounted(() => {
  load()
})
</script>

<style scoped>
.watchlist {
  padding: 24px;
  height: 100%;
  overflow-y: auto;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.header h1 {
  font-size: 20px;
  font-weight: 600;
}

.group {
  margin-bottom: 24px;
}

.group-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
  font-weight: 600;
  color: #9ca3af;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #1f2937;
}

.group-actions {
  display: flex;
  gap: 10px;
}

.group-items {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

.stock-card {
  background: #1f2937;
  border-radius: 8px;
  padding: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.stock-name {
  font-size: 15px;
  font-weight: 500;
  color: #fff;
  margin-bottom: 4px;
}

.stock-code {
  font-size: 12px;
  color: #9ca3af;
  font-weight: normal;
}

.stock-meta {
  font-size: 12px;
  color: #9ca3af;
  margin-bottom: 6px;
}

.stock-quote {
  display: flex;
  gap: 12px;
  font-size: 13px;
}

.stock-quote .up {
  color: #ef4444;
}

.stock-quote .down {
  color: #22c55e;
}

.turnover {
  color: #9ca3af;
}

.stock-actions {
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

.btn-link.danger {
  color: #f87171;
}

.btn-link.danger:hover {
  color: #fca5a5;
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

.btn-secondary:hover {
  background: #374151;
}

.empty {
  color: #9ca3af;
  text-align: center;
  padding: 60px 0;
}

.empty a {
  color: #60a5fa;
  text-decoration: none;
}
</style>
