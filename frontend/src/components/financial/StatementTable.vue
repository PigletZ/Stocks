<template>
  <div class="statement-table panel">
    <div class="st-toolbar">
      <div class="st-stock-tabs">
        <button
          v-for="s in stocks"
          :key="s.code"
          class="tab-btn"
          :class="{ active: activeCode === s.code }"
          @click="switchStock(s.code)"
        >{{ s.name }}</button>
      </div>
      <div class="st-right">
        <div class="st-type-tabs">
          <button
            v-for="t in TYPE_TABS"
            :key="t.key"
            class="tab-btn"
            :class="{ active: activeType === t.key }"
            @click="switchType(t.key)"
          >{{ t.label }}</button>
        </div>
        <select v-model="unit">
          <option value="yi">单位: 亿元</option>
          <option value="yuan">单位: 元</option>
        </select>
      </div>
    </div>

    <div v-if="loading" class="st-hint">加载中…</div>
    <div v-else-if="error" class="st-hint error">{{ error }}</div>
    <div v-else-if="!data || !data.items.length" class="st-hint">暂无报表数据</div>
    <div v-else class="st-scroll">
      <table>
        <thead>
          <tr>
            <th class="col-name">科目</th>
            <th v-for="p in data.periods" :key="p">{{ p }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in data.items" :key="item.field">
            <td class="col-name" :title="item.field">{{ item.name }}</td>
            <td v-for="(v, i) in item.values" :key="i">
              <div class="cell-val">{{ fmtVal(v) }}</div>
              <div v-if="item.yoy[i] !== null" class="cell-yoy" :class="yoyClass(item.yoy[i])">
                {{ fmtYoy(item.yoy[i]) }}
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  fetchFinancialStatements,
  type FinStatementResult,
  type FinStockCompare,
} from '../../api/client'

const TYPE_TABS = [
  { key: 'income' as const, label: '利润表' },
  { key: 'balance' as const, label: '资产负债表' },
  { key: 'cashflow' as const, label: '现金流量表' },
]

const props = defineProps<{ stocks: FinStockCompare[] }>()

const activeCode = ref('')
const activeType = ref<'income' | 'balance' | 'cashflow'>('income')
const unit = ref<'yi' | 'yuan'>('yi')
const data = ref<FinStatementResult | null>(null)
const loading = ref(false)
const error = ref('')

// 缓存已加载的报表: `${code}:${type}`
const cache = new Map<string, FinStatementResult>()

async function load() {
  if (!activeCode.value) return
  const key = `${activeCode.value}:${activeType.value}`
  const hit = cache.get(key)
  if (hit) {
    data.value = hit
    return
  }
  loading.value = true
  error.value = ''
  try {
    const res = await fetchFinancialStatements(activeCode.value, activeType.value)
    cache.set(key, res)
    data.value = res
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
    data.value = null
  } finally {
    loading.value = false
  }
}

function switchStock(code: string) {
  activeCode.value = code
  load()
}

function switchType(t: 'income' | 'balance' | 'cashflow') {
  activeType.value = t
  load()
}

watch(
  () => props.stocks,
  (ss) => {
    if (!ss.length) {
      activeCode.value = ''
      data.value = null
      return
    }
    if (!ss.some((s) => s.code === activeCode.value)) {
      activeCode.value = ss[0].code
      load()
    }
  },
  { immediate: true }
)

function fmtVal(v: number | null): string {
  if (v === null || v === undefined) return '-'
  if (unit.value === 'yi') return (v / 1e8).toFixed(2)
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function fmtYoy(v: number | null): string {
  if (v === null || v === undefined) return ''
  return (v >= 0 ? '+' : '') + (v * 100).toFixed(1) + '%'
}

function yoyClass(v: number | null): string {
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

.st-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 10px;
}

.st-stock-tabs,
.st-type-tabs {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.st-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.tab-btn {
  background: #1f2937;
  border: 1px solid #374151;
  border-radius: 4px;
  color: #d1d5db;
  font-size: 13px;
  padding: 5px 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.tab-btn:hover {
  color: #fff;
}

.tab-btn.active {
  background: #2563eb;
  border-color: #2563eb;
  color: #fff;
}

select {
  background: #1f2937;
  border: 1px solid #374151;
  border-radius: 4px;
  color: #e5e7eb;
  font-size: 13px;
  padding: 4px 8px;
}

.st-hint {
  color: #6b7280;
  font-size: 13px;
  text-align: center;
  padding: 40px 0;
}

.st-hint.error {
  color: #f87171;
}

.st-scroll {
  overflow-x: auto;
  max-height: 560px;
  overflow-y: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

th,
td {
  padding: 6px 10px;
  text-align: right;
  border-bottom: 1px solid #1f2937;
  white-space: nowrap;
}

th {
  color: #d1d5db;
  font-weight: 600;
  background: #0b0f19;
  position: sticky;
  top: 0;
  z-index: 2;
}

.col-name {
  text-align: left;
  color: #9ca3af;
  position: sticky;
  left: 0;
  background: #111827;
  z-index: 1;
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
}

th.col-name {
  background: #0b0f19;
  z-index: 3;
}

.cell-val {
  color: #e5e7eb;
}

.cell-yoy {
  font-size: 11px;
}

.cell-yoy.up {
  color: #ef4444;
}

.cell-yoy.down {
  color: #22c55e;
}
</style>
