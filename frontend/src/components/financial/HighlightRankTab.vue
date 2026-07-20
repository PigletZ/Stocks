<template>
  <div class="highlight-rank panel">
    <div class="hr-header">
      <h3>亮点 Top{{ items.length }} 榜</h3>
      <select v-model="limit" @change="load">
        <option :value="100">前 100</option>
        <option :value="200">前 200</option>
        <option :value="300">前 300</option>
      </select>
      <span v-if="rankDate" class="hr-date">榜单日期：{{ rankDate }}</span>
    </div>

    <div v-if="loading" class="hr-hint">加载中…</div>
    <div v-else-if="!items.length" class="hr-hint">暂无榜单数据（等待每日 19:00 增量任务算榜）</div>
    <div v-else class="hr-scroll">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>代码</th>
            <th>名称</th>
            <th>行业</th>
            <th class="num">亮点</th>
            <th class="num">风险</th>
            <th>标签</th>
            <th class="num">营收同比</th>
            <th class="num">净利同比</th>
            <th class="num">ROE(年化)</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="it in items" :key="it.code">
            <td class="rank" :class="{ top3: it.rank <= 3 }">{{ it.rank }}</td>
            <td class="code">{{ it.code }}</td>
            <td class="name">{{ it.name }}</td>
            <td class="industry">{{ it.industry || '-' }}</td>
            <td class="num good">{{ it.good_count }}</td>
            <td class="num" :class="{ risk: it.risk_count > 0 }">{{ it.risk_count }}</td>
            <td class="tags">
              <span
                v-for="t in it.tags"
                :key="t.label"
                class="tag"
                :class="t.type"
              >{{ t.label }}</span>
            </td>
            <td class="num" :class="cls(it.metrics.revenue_yoy)">{{ fmtPct(it.metrics.revenue_yoy) }}</td>
            <td class="num" :class="cls(it.metrics.net_profit_yoy)">{{ fmtPct(it.metrics.net_profit_yoy) }}</td>
            <td class="num">{{ fmtPct(it.metrics.roe_annualized, false) }}</td>
            <td>
              <button class="btn-compare" @click="$emit('compare', { code: it.code, name: it.name })">
                加入对比
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { fetchFinancialHighlightRank, type FinHighlightItem } from '../../api/client'

defineEmits<{ (e: 'compare', stock: { code: string; name: string }): void }>()

const items = ref<FinHighlightItem[]>([])
const rankDate = ref<string | null>(null)
const loading = ref(true)
const limit = ref(100)

async function load() {
  loading.value = true
  try {
    const res = await fetchFinancialHighlightRank(limit.value)
    items.value = res.items
    rankDate.value = res.date
  } finally {
    loading.value = false
  }
}

onMounted(load)

function fmtPct(v?: number | null, signed = true): string {
  if (v === null || v === undefined) return '-'
  const pct = (v * 100).toFixed(1) + '%'
  return signed && v >= 0 ? '+' + pct : pct
}

function cls(v?: number | null): string {
  if (v === null || v === undefined) return ''
  return v >= 0 ? 'up' : 'down'
}
</script>

<style scoped>
.panel {
  background: #111827;
  border: 1px solid #1f2937;
  border-radius: 8px;
  padding: 14px 16px;
}

.hr-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 10px;
}

.hr-header h3 {
  color: #e5e7eb;
  font-size: 15px;
  margin: 0;
}

.hr-date {
  color: #6b7280;
  font-size: 12px;
}

.hr-header select {
  background: #1f2937;
  border: 1px solid #374151;
  border-radius: 4px;
  color: #e5e7eb;
  font-size: 13px;
  padding: 4px 8px;
}

.hr-hint {
  color: #6b7280;
  font-size: 13px;
  text-align: center;
  padding: 40px 0;
}

.hr-scroll {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

th,
td {
  padding: 7px 10px;
  border-bottom: 1px solid #1f2937;
  white-space: nowrap;
  text-align: left;
}

th {
  color: #d1d5db;
  font-weight: 600;
  background: #0b0f19;
  position: sticky;
  top: 0;
}

th.num,
td.num {
  text-align: right;
}

.rank {
  color: #9ca3af;
  font-weight: 600;
}

.rank.top3 {
  color: #f59e0b;
}

.code {
  color: #60a5fa;
}

.name {
  color: #ffffff;
  font-weight: 600;
}

.industry {
  color: #9ca3af;
  font-size: 12px;
}

td.good {
  color: #f87171;
  font-weight: 700;
}

td.risk {
  color: #4ade80;
  font-weight: 700;
}

td.up {
  color: #ef4444;
}

td.down {
  color: #22c55e;
}

.tags {
  max-width: 340px;
  white-space: normal;
}

.tag {
  display: inline-block;
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 3px;
  margin: 1px 3px 1px 0;
}

.tag.good {
  background: rgba(239, 68, 68, 0.12);
  color: #f87171;
  border: 1px solid rgba(239, 68, 68, 0.35);
}

.tag.risk {
  background: rgba(34, 197, 94, 0.12);
  color: #4ade80;
  border: 1px solid rgba(34, 197, 94, 0.35);
}

.btn-compare {
  background: #1f2937;
  border: 1px solid #374151;
  border-radius: 4px;
  color: #60a5fa;
  font-size: 12px;
  padding: 4px 10px;
  cursor: pointer;
}

.btn-compare:hover {
  background: #2563eb;
  border-color: #2563eb;
  color: #fff;
}
</style>
