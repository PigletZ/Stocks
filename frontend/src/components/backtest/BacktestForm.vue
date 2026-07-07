<template>
  <div class="backtest-form">
    <div class="field">
      <label>策略</label>
      <select v-model="form.strategy_id" disabled>
        <option value="piglet">首板不破·龙头跟踪</option>
      </select>
      <p class="desc">当前仅支持 piglet 策略</p>
    </div>

    <div class="field">
      <label>开始日期</label>
      <input type="date" v-model="form.start_date" />
      <p class="desc">&nbsp;</p>
    </div>

    <div class="field">
      <label>结束日期</label>
      <input type="date" v-model="form.end_date" />
      <p class="desc">&nbsp;</p>
    </div>

    <div class="field field-small">
      <label>窗口天数</label>
      <input type="number" v-model.number="form.window_days" min="2" max="60" />
      <p class="desc">选股回看窗口</p>
    </div>

    <div class="field field-small">
      <label>持仓天数</label>
      <input type="number" v-model.number="form.hold_days" min="1" max="60" />
      <p class="desc">买入后持有</p>
    </div>

    <div class="field field-small">
      <label>最大持仓</label>
      <input type="number" v-model.number="form.max_positions" min="1" max="50" />
      <p class="desc">同时持仓上限</p>
    </div>

    <div class="field field-small">
      <label>每日买入</label>
      <input type="number" v-model.number="form.max_per_day" min="1" max="20" />
      <p class="desc">每信号日最多</p>
    </div>

    <div class="field field-small">
      <label>初始资金</label>
      <input type="number" v-model.number="form.initial_capital" min="10000" step="10000" />
      <p class="desc">元</p>
    </div>

    <div class="field field-small">
      <label>佣金率</label>
      <input type="number" v-model.number="form.commission_rate" min="0" max="0.1" step="0.0001" />
      <p class="desc">双边</p>
    </div>

    <div class="field field-checkbox">
      <label>
        <input type="checkbox" v-model="form.require_dragon" />
        仅游资介入
      </label>
      <p class="desc">只交易有龙虎榜的股票</p>
    </div>

    <div class="field field-button">
      <label>&nbsp;</label>
      <button
        class="btn-primary run-btn"
        :disabled="loading"
        @click="$emit('run', form)"
      >
        {{ loading ? '回测中...' : '运行回测' }}
      </button>
      <p class="desc">&nbsp;</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import type { BacktestRequest } from '../../api/client'

defineProps<{
  loading: boolean
}>()

defineEmits<{
  (e: 'run', req: BacktestRequest): void
}>()

// 默认回测最近 15 天（实时 Tushare 模式暂限制最大 15 天）
const today = new Date()
const startDay = new Date(today.getTime() - 15 * 24 * 60 * 60 * 1000)

function fmt(d: Date) {
  return d.toISOString().split('T')[0]
}

const form = reactive<BacktestRequest>({
  strategy_id: 'piglet',
  start_date: fmt(startDay),
  end_date: fmt(today),
  window_days: 5,
  hold_days: 5,
  max_positions: 5,
  max_per_day: 2,
  require_dragon: false,
  initial_capital: 100000,
  commission_rate: 0.0003,
})
</script>

<style scoped>
.backtest-form {
  display: flex;
  align-items: flex-end;
  gap: 16px;
  flex-wrap: wrap;
  background: #111827;
  border: 1px solid #1f2937;
  border-radius: 8px;
  padding: 20px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 140px;
  flex: 1;
}

.field-small {
  min-width: 90px;
  flex: 0 1 90px;
}

.field-checkbox {
  min-width: 110px;
  flex: 0 1 110px;
  padding-bottom: 24px;
}

.field label {
  font-size: 13px;
  color: #9ca3af;
}

.field-checkbox label {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  color: #e5e7eb;
}

.field select,
.field input[type='date'],
.field input[type='number'] {
  padding: 8px 10px;
  background: #0b0f19;
  border: 1px solid #374151;
  border-radius: 6px;
  color: #e5e7eb;
  font-size: 14px;
}

.field input[type='checkbox'] {
  width: 16px;
  height: 16px;
  accent-color: #2563eb;
}

.field .desc {
  font-size: 12px;
  color: #6b7280;
  margin: 0;
}

.field-button {
  flex: 0 0 auto;
  min-width: auto;
}

.run-btn {
  height: 38px;
  padding: 0 24px;
  white-space: nowrap;
}

.btn-primary {
  background: #2563eb;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-primary:hover:not(:disabled) {
  background: #1d4ed8;
}

.btn-primary:disabled {
  background: #1e3a8a;
  color: #93c5fd;
  cursor: not-allowed;
}
</style>
