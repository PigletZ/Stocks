<template>
  <div class="health-card">
    <div class="hc-header">
      <span class="hc-name">{{ stock.name }}</span>
      <span class="hc-code">{{ stock.code }}</span>
      <span class="hc-period">{{ stock.card.period || '' }}</span>
    </div>
    <div class="hc-metrics">
      <div class="hc-metric" v-for="m in metricList" :key="m.label">
        <div class="hc-m-label">{{ m.label }}</div>
        <div class="hc-m-value">{{ m.value }}</div>
        <div v-if="m.yoy !== undefined" class="hc-m-yoy" :class="m.yoyClass">{{ m.yoy }}</div>
      </div>
    </div>
    <div class="hc-tags">
      <span
        v-for="t in stock.tags"
        :key="t.label"
        class="hc-tag"
        :class="t.type"
      >{{ t.type === 'good' ? '✓' : '⚠' }} {{ t.label }}</span>
      <span v-if="!stock.tags.length" class="hc-tag-none">暂无标签</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { FinStockCompare } from '../../api/client'

const props = defineProps<{ stock: FinStockCompare }>()

function fmtYi(v?: number | null): string {
  if (v === null || v === undefined) return '-'
  return (v / 1e8).toFixed(2) + '亿'
}

function fmtPct(v?: number | null, digits = 1): string | undefined {
  if (v === null || v === undefined) return undefined
  return (v >= 0 ? '+' : '') + (v * 100).toFixed(digits) + '%'
}

function fmtRatioPct(v?: number | null): string {
  if (v === null || v === undefined) return '-'
  return (v * 100).toFixed(1) + '%'
}

const metricList = computed(() => {
  const c = props.stock.card
  return [
    { label: '营业总收入', value: fmtYi(c.revenue), yoy: fmtPct(c.revenue_yoy), yoyClass: cls(c.revenue_yoy) },
    { label: '归母净利润', value: fmtYi(c.net_profit), yoy: fmtPct(c.net_profit_yoy), yoyClass: cls(c.net_profit_yoy) },
    { label: 'ROE(年化)', value: fmtRatioPct(c.roe_annualized) },
    { label: '毛利率', value: fmtRatioPct(c.gross_margin) },
    { label: '资产负债率', value: fmtRatioPct(c.debt_ratio) },
    { label: '经营现金流', value: fmtYi(c.ncf) },
  ]
})

function cls(v?: number | null): string {
  if (v === null || v === undefined) return ''
  return v >= 0 ? 'up' : 'down'
}
</script>

<style scoped>
.health-card {
  background: #111827;
  border: 1px solid #1f2937;
  border-radius: 8px;
  padding: 14px 16px;
  min-width: 300px;
  flex: 1;
}

.hc-header {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 12px;
}

.hc-name {
  color: #ffffff;
  font-size: 15px;
  font-weight: 700;
}

.hc-code {
  color: #60a5fa;
  font-size: 12px;
}

.hc-period {
  margin-left: auto;
  color: #6b7280;
  font-size: 12px;
}

.hc-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px 12px;
  margin-bottom: 12px;
}

.hc-m-label {
  color: #9ca3af;
  font-size: 12px;
  margin-bottom: 2px;
}

.hc-m-value {
  color: #e5e7eb;
  font-size: 15px;
  font-weight: 600;
}

.hc-m-yoy {
  font-size: 12px;
}

.hc-m-yoy.up {
  color: #ef4444;
}

.hc-m-yoy.down {
  color: #22c55e;
}

.hc-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.hc-tag {
  font-size: 12px;
  padding: 3px 8px;
  border-radius: 4px;
}

.hc-tag.good {
  background: rgba(239, 68, 68, 0.12);
  color: #f87171;
  border: 1px solid rgba(239, 68, 68, 0.35);
}

.hc-tag.risk {
  background: rgba(34, 197, 94, 0.12);
  color: #4ade80;
  border: 1px solid rgba(34, 197, 94, 0.35);
}

.hc-tag-none {
  color: #6b7280;
  font-size: 12px;
}
</style>
