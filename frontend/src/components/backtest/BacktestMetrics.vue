<template>
  <div class="metrics-grid">
    <div class="metric-card highlight">
      <div class="label">总收益</div>
      <div class="value" :class="pctClass(metrics?.total_return_pct)">{{ formatPct(metrics?.total_return_pct) }}</div>
    </div>

    <div class="metric-card">
      <div class="label">年化收益</div>
      <div class="value" :class="pctClass(metrics?.cagr_pct)">{{ formatPct(metrics?.cagr_pct) }}</div>
    </div>

    <div class="metric-card">
      <div class="label">最大回撤</div>
      <div class="value down">{{ formatPct(metrics?.max_drawdown_pct, true) }}</div>
    </div>

    <div class="metric-card">
      <div class="label">夏普比率</div>
      <div class="value">{{ metrics?.sharpe_ratio?.toFixed(2) ?? '-' }}</div>
    </div>

    <div class="metric-card">
      <div class="label">胜率</div>
      <div class="value">{{ metrics?.win_rate_pct?.toFixed(2) ?? '-' }}%</div>
    </div>

    <div class="metric-card">
      <div class="label">盈亏比</div>
      <div class="value">{{ metrics?.profit_factor?.toFixed(2) ?? '-' }}</div>
    </div>

    <div class="metric-card">
      <div class="label">交易次数</div>
      <div class="value">{{ metrics?.num_sell_trades ?? '-' }}</div>
    </div>

    <div class="metric-card">
      <div class="label">平均持仓天数</div>
      <div class="value">{{ metrics?.avg_hold_days?.toFixed(2) ?? '-' }}</div>
    </div>

    <div class="metric-card">
      <div class="label">最终权益</div>
      <div class="value">{{ formatAmount(metrics?.final_value) }}</div>
    </div>

    <div class="metric-card">
      <div class="label">平均每笔盈亏</div>
      <div class="value" :class="pnlClass(metrics?.avg_trade_pnl)">{{ formatAmount(metrics?.avg_trade_pnl) }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { BacktestMetrics } from '../../api/client'

defineProps<{
  metrics?: BacktestMetrics
}>()

function formatPct(pct?: number | null, absolute = false) {
  if (pct === null || pct === undefined) return '-'
  const value = absolute ? Math.abs(pct) : pct
  const sign = !absolute && value > 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}%`
}

function formatAmount(amount?: number | null) {
  if (amount === null || amount === undefined) return '-'
  return amount.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function pctClass(pct?: number | null) {
  if (pct === null || pct === undefined) return ''
  return pct > 0 ? 'up' : pct < 0 ? 'down' : ''
}

function pnlClass(pnl?: number | null) {
  if (pnl === null || pnl === undefined) return ''
  return pnl > 0 ? 'up' : pnl < 0 ? 'down' : ''
}
</script>

<style scoped>
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
}

.metric-card {
  background: #111827;
  border: 1px solid #1f2937;
  border-radius: 8px;
  padding: 16px;
}

.metric-card.highlight {
  border-color: #2563eb;
}

.label {
  font-size: 12px;
  color: #9ca3af;
  margin-bottom: 8px;
}

.value {
  font-size: 20px;
  font-weight: 600;
  color: #fff;
}

.value.up {
  color: #ef4444;
}

.value.down {
  color: #22c55e;
}
</style>
