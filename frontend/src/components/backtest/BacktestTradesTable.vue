<template>
  <div class="trades-table">
    <table>
      <thead>
        <tr>
          <th>方向</th>
          <th>股票</th>
          <th>交易日期</th>
          <th>信号日期</th>
          <th>价格</th>
          <th>数量</th>
          <th>成交额</th>
          <th>佣金</th>
          <th v-if="showPnl">盈亏</th>
          <th>首板日期</th>
          <th>游资介入</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="trades.length === 0">
          <td :colspan="11" class="empty">暂无交易记录</td>
        </tr>
        <tr
          v-for="t in sortedTrades"
          :key="t.id"
          :class="t.direction"
        >
          <td>
            <span class="tag" :class="t.direction">{{ t.direction === 'buy' ? '买入' : '卖出' }}</span>
          </td>
          <td>
            <div class="stock-name">{{ t.stock_name || t.stock_code }}</div>
            <div class="stock-code">{{ t.stock_code }}</div>
          </td>
          <td>{{ formatDate(t.trade_date) }}</td>
          <td>{{ formatDate(t.signal_date) }}</td>
          <td>{{ formatNumber(t.price) }}</td>
          <td>{{ t.quantity ?? '-' }}</td>
          <td>{{ formatAmount(t.amount) }}</td>
          <td>{{ formatNumber(t.commission) }}</td>
          <td v-if="showPnl" :class="pnlClass(t.pnl)">{{ formatPnl(t.pnl) }}</td>
          <td>{{ formatDate(t.raw?.first_limit_date) }}</td>
          <td>
            <span v-if="t.raw?.has_dragon" class="tag-dragon">游资</span>
            <span v-else class="tag-none">无</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { BacktestTradeItem } from '../../api/client'

const props = defineProps<{
  trades: BacktestTradeItem[]
}>()

const showPnl = computed(() => props.trades.some((t) => t.direction === 'sell'))

const sortedTrades = computed(() => {
  return [...props.trades].sort((a, b) => {
    if (a.trade_date !== b.trade_date) {
      return a.trade_date.localeCompare(b.trade_date)
    }
    return a.direction.localeCompare(b.direction)
  })
})

function formatDate(d?: string | null) {
  if (!d) return '-'
  return d.length >= 10 ? d.slice(5) : d
}

function formatNumber(n?: number | null) {
  if (n === null || n === undefined) return '-'
  return n.toFixed(2)
}

function formatAmount(amount?: number | null) {
  if (amount === null || amount === undefined) return '-'
  return amount.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatPnl(pnl?: number | null) {
  if (pnl === null || pnl === undefined) return '-'
  const sign = pnl > 0 ? '+' : ''
  return `${sign}${pnl.toFixed(2)}`
}

function pnlClass(pnl?: number | null) {
  if (pnl === null || pnl === undefined) return ''
  return pnl > 0 ? 'up' : pnl < 0 ? 'down' : ''
}
</script>

<style scoped>
.trades-table {
  background: #111827;
  border: 1px solid #1f2937;
  border-radius: 8px;
  overflow-x: auto;
}

.empty {
  padding: 40px;
  text-align: center;
  color: #6b7280;
  font-size: 14px;
}

table {
  width: 100%;
  min-width: 900px;
  border-collapse: collapse;
  font-size: 13px;
}

th,
td {
  padding: 12px 14px;
  text-align: left;
  border-bottom: 1px solid #1f2937;
}

th {
  background: #0b0f19;
  color: #9ca3af;
  font-weight: 500;
  font-size: 12px;
}

td {
  color: #e5e7eb;
}

tr.sell td {
  background: rgba(34, 197, 94, 0.05);
}

.tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}

.tag.buy {
  background: rgba(239, 68, 68, 0.15);
  color: #f87171;
}

.tag.sell {
  background: rgba(34, 197, 94, 0.15);
  color: #4ade80;
}

.tag-dragon {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(239, 68, 68, 0.15);
  color: #f87171;
  font-size: 12px;
  font-weight: 600;
}

.tag-none {
  color: #6b7280;
  font-size: 12px;
}

.stock-name {
  font-weight: 500;
  color: #fff;
}

.stock-code {
  font-size: 12px;
  color: #9ca3af;
  margin-top: 2px;
}

td.up {
  color: #ef4444;
  font-weight: 600;
}

td.down {
  color: #22c55e;
  font-weight: 600;
}
</style>
