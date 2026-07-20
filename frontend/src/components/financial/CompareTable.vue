<template>
  <div class="compare-table panel">
    <div class="ct-header">
      <h3>指标对比</h3>
      <div class="ct-period">
        <label>报告期</label>
        <select v-model="selectedPeriod">
          <option v-for="p in periods" :key="p" :value="p">{{ p }}</option>
        </select>
      </div>
    </div>
    <div class="ct-scroll">
      <table>
        <thead>
          <tr>
            <th class="col-metric">指标</th>
            <th v-for="s in stocks" :key="s.code">{{ s.name }}<em>{{ s.code }}</em></th>
          </tr>
        </thead>
        <tbody>
          <template v-for="group in groups" :key="group.name">
            <tr class="group-row" @click="toggle(group.name)">
              <td :colspan="stocks.length + 1">
                <span class="group-arrow" :class="{ open: !collapsed.has(group.name) }">▶</span>
                {{ group.name }}
              </td>
            </tr>
            <tr v-for="m in group.metrics" :key="m.key" v-show="!collapsed.has(group.name)">
              <td class="col-metric">{{ m.label }}</td>
              <td
                v-for="(s, i) in stocks"
                :key="s.code"
                :class="cellClass(m, i)"
              >{{ format(m, metricsOf(s)[m.key]) }}</td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { FinMetrics, FinStockCompare } from '../../api/client'

interface MetricDef {
  key: keyof FinMetrics
  label: string
  format: 'pct' | 'yi' | 'times' | 'ratio'
  lowerBetter?: boolean
}

const props = defineProps<{ stocks: FinStockCompare[] }>()

const groups: { name: string; metrics: MetricDef[] }[] = [
  {
    name: '规模',
    metrics: [
      { key: 'revenue', label: '营业总收入', format: 'yi' },
      { key: 'net_profit', label: '归母净利润', format: 'yi' },
    ],
  },
  {
    name: '盈利能力',
    metrics: [
      { key: 'gross_margin', label: '毛利率', format: 'pct' },
      { key: 'net_margin', label: '净利率', format: 'pct' },
      { key: 'roe_annualized', label: 'ROE(年化)', format: 'pct' },
    ],
  },
  {
    name: '成长能力',
    metrics: [
      { key: 'revenue_yoy', label: '营收同比', format: 'pct', },
      { key: 'net_profit_yoy', label: '归母净利同比', format: 'pct' },
    ],
  },
  {
    name: '偿债能力',
    metrics: [
      { key: 'debt_ratio', label: '资产负债率', format: 'pct', lowerBetter: true },
      { key: 'current_ratio', label: '流动比率', format: 'ratio' },
    ],
  },
  {
    name: '现金流',
    metrics: [
      { key: 'ncf', label: '经营现金流净额', format: 'yi' },
      { key: 'ncf_ratio', label: '净现比', format: 'ratio' },
    ],
  },
  {
    name: '运营效率',
    metrics: [
      { key: 'inv_turnover', label: '存货周转率', format: 'times' },
      { key: 'ar_turnover', label: '应收账款周转率', format: 'times' },
      { key: 'asset_turnover', label: '总资产周转率', format: 'times' },
    ],
  },
  {
    name: '风险',
    metrics: [{ key: 'goodwill_ratio', label: '商誉/归母权益', format: 'pct', lowerBetter: true }],
  },
]

// 所有股票展示期的并集（新→旧）
const periods = computed(() => {
  const set = new Set<string>()
  props.stocks.forEach((s) => s.periods.forEach((p) => set.add(p)))
  return Array.from(set).sort().reverse()
})

const selectedPeriod = ref('')
watch(
  periods,
  (ps) => {
    if (!selectedPeriod.value || !ps.includes(selectedPeriod.value)) {
      selectedPeriod.value = ps[0] || ''
    }
  },
  { immediate: true }
)

const collapsed = ref(new Set<string>())
function toggle(name: string) {
  const next = new Set(collapsed.value)
  if (next.has(name)) next.delete(name)
  else next.add(name)
  collapsed.value = next
}

function metricsOf(s: FinStockCompare): FinMetrics {
  return s.metrics[selectedPeriod.value] || {}
}

function format(m: MetricDef, v?: number | null): string {
  if (v === null || v === undefined) return '-'
  switch (m.format) {
    case 'pct':
      return (v * 100).toFixed(1) + '%'
    case 'yi':
      return (v / 1e8).toFixed(2)
    case 'times':
      return v.toFixed(2)
    case 'ratio':
      return v.toFixed(2)
  }
}

// 每行最优/最差高亮（有效值 ≥2 个才标）
function cellClass(m: MetricDef, idx: number): string {
  const vals = props.stocks.map((s) => metricsOf(s)[m.key])
  const valid = vals.filter((v): v is number => v !== null && v !== undefined)
  if (valid.length < 2) return ''
  const v = vals[idx]
  if (v === null || v === undefined) return ''
  const best = m.lowerBetter ? Math.min(...valid) : Math.max(...valid)
  const worst = m.lowerBetter ? Math.max(...valid) : Math.min(...valid)
  if (v === best && best !== worst) return 'best'
  if (v === worst && best !== worst) return 'worst'
  return ''
}
</script>

<style scoped>
.panel {
  background: #111827;
  border: 1px solid #1f2937;
  border-radius: 8px;
  padding: 14px 16px;
}

.ct-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.ct-header h3 {
  color: #e5e7eb;
  font-size: 15px;
  margin: 0;
}

.ct-period {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #9ca3af;
  font-size: 13px;
}

.ct-period select {
  background: #1f2937;
  border: 1px solid #374151;
  border-radius: 4px;
  color: #e5e7eb;
  font-size: 13px;
  padding: 4px 8px;
}

.ct-scroll {
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
}

th em {
  display: block;
  font-style: normal;
  color: #60a5fa;
  font-size: 11px;
  font-weight: 400;
}

.col-metric {
  text-align: left;
  color: #9ca3af;
}

td {
  color: #e5e7eb;
}

.group-row {
  cursor: pointer;
  background: rgba(37, 99, 235, 0.06);
}

.group-row td {
  text-align: left;
  color: #93c5fd;
  font-weight: 600;
  user-select: none;
}

.group-arrow {
  display: inline-block;
  font-size: 10px;
  margin-right: 6px;
  transition: transform 0.15s;
}

.group-arrow.open {
  transform: rotate(90deg);
}

td.best {
  color: #f87171;
  font-weight: 700;
}

td.worst {
  color: #4ade80;
}
</style>
