<template>
  <div class="backtest-page">
    <header class="page-header">
      <h1>策略回测</h1>
      <div class="tab-nav">
        <button class="tab-btn" :class="{ active: tab === 'single' }" @click="tab = 'single'">单次回测</button>
        <button class="tab-btn" :class="{ active: tab === 'grid' }" @click="tab = 'grid'">网格寻优</button>
        <button class="tab-btn" :class="{ active: tab === 'history' }" @click="switchTab('history')">历史记录</button>
      </div>
    </header>

    <!-- 单次回测 -->
    <div v-show="tab === 'single'">
      <BacktestForm :loading="loading" @run="handleRunBacktest" />

      <div v-if="error" class="error-message">{{ error }}</div>

      <div v-if="result" class="result-section">
        <div class="result-header">
          <h2>回测结果</h2>
          <span class="result-meta">
            {{ result.start_date }} ~ {{ result.end_date }} · {{ result.status === 'completed' ? '完成' : result.status }}
            <template v-if="result.params?.data_source"> · 数据源：{{ result.params.data_source === 'local' ? '本地缓存' : '实时Tushare' }}</template>
          </span>
        </div>

        <BacktestMetrics :metrics="result.metrics" />

        <div class="chart-section">
          <h3>权益曲线</h3>
          <EquityCurveChart :equity-curve="result.equity_curve" />
        </div>

        <div class="chart-section">
          <h3>回撤曲线（%）</h3>
          <EquityCurveChart :equity-curve="drawdownCurve" />
        </div>

        <div class="trades-section">
          <div class="trades-header">
            <h3>交易明细（点击行查看 K 线）</h3>
            <span class="result-meta">共 {{ (result.trades || []).length }} 笔</span>
          </div>
          <BacktestTradesTable :trades="result.trades || []" @show-detail="onShowTradeDetail" />
        </div>
      </div>
    </div>

    <!-- 网格寻优 -->
    <div v-show="tab === 'grid'">
      <div class="panel">
        <div class="panel-title">参数网格（逗号分隔多个值，组合上限 24 个）</div>
        <div class="grid-form">
          <div class="field">
            <label>开始日期</label>
            <input type="date" v-model="gridForm.start_date" />
          </div>
          <div class="field">
            <label>结束日期</label>
            <input type="date" v-model="gridForm.end_date" />
          </div>
          <div class="field">
            <label>窗口天数</label>
            <input v-model="gridForm.window_days" placeholder="如 3,5,8" />
          </div>
          <div class="field">
            <label>持仓天数</label>
            <input v-model="gridForm.hold_days" placeholder="如 3,5,10" />
          </div>
          <div class="field">
            <label>最大持仓</label>
            <input v-model="gridForm.max_positions" placeholder="如 5" />
          </div>
          <div class="field">
            <label>每日买入</label>
            <input v-model="gridForm.max_per_day" placeholder="如 2" />
          </div>
          <div class="field">
            <label>初始资金</label>
            <input type="number" v-model.number="gridForm.initial_capital" step="10000" />
          </div>
          <div class="field">
            <label>&nbsp;</label>
            <button class="btn-primary" @click="handleRunGrid" :disabled="gridLoading">
              {{ gridLoading ? `执行中 ${gridDone}/${gridTotal}` : '开始寻优' }}
            </button>
          </div>
        </div>
        <div v-if="gridError" class="error-message">{{ gridError }}</div>
      </div>

      <div v-if="gridResults.length" class="panel">
        <div class="panel-title">寻优结果对比（按总收益降序）</div>
        <table class="result-table">
          <thead>
            <tr>
              <th>#</th><th>窗口</th><th>持仓</th><th>最大持仓</th><th>每日买入</th>
              <th>总收益</th><th>年化</th><th>最大回撤</th><th>夏普</th><th>胜率</th><th>状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in gridResults" :key="r.id" class="clickable" @click="loadRun(r.id)">
              <td>{{ i + 1 }}</td>
              <td>{{ r.params.window_days }}</td>
              <td>{{ r.params.hold_days }}</td>
              <td>{{ r.params.max_positions }}</td>
              <td>{{ r.params.max_per_day }}</td>
              <td :class="pctClass(r.metrics?.total_return_pct)">{{ fmtPct(r.metrics?.total_return_pct) }}</td>
              <td :class="pctClass(r.metrics?.cagr_pct)">{{ fmtPct(r.metrics?.cagr_pct) }}</td>
              <td class="down">{{ fmtPct(r.metrics?.max_drawdown_pct) }}</td>
              <td>{{ r.metrics?.sharpe_ratio?.toFixed(2) ?? '-' }}</td>
              <td>{{ r.metrics ? (r.metrics.win_rate * 100).toFixed(1) + '%' : '-' }}</td>
              <td class="muted">{{ statusText(r.status) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 历史记录 -->
    <div v-show="tab === 'history'">
      <div class="panel">
        <div class="panel-title">历史回测（点击查看详情）</div>
        <div v-if="!history.length" class="empty">暂无历史记录</div>
        <table v-else class="result-table">
          <thead>
            <tr>
              <th>ID</th><th>区间</th><th>参数</th><th>总收益</th><th>最大回撤</th><th>胜率</th><th>数据源</th><th>状态</th><th>创建时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in history" :key="r.id" class="clickable" @click="loadRun(r.id)">
              <td class="muted">{{ r.id }}</td>
              <td>{{ r.start_date }} ~ {{ r.end_date }}</td>
              <td class="muted">{{ paramsText(r.params) }}</td>
              <td :class="pctClass(r.metrics?.total_return_pct)">{{ fmtPct(r.metrics?.total_return_pct) }}</td>
              <td class="down">{{ fmtPct(r.metrics?.max_drawdown_pct) }}</td>
              <td>{{ r.metrics ? (r.metrics.win_rate * 100).toFixed(1) + '%' : '-' }}</td>
              <td class="muted">{{ r.params?.data_source === 'local' ? '本地' : r.params?.data_source === 'tushare' ? '实时' : '-' }}</td>
              <td class="muted">{{ statusText(r.status) }}</td>
              <td class="muted">{{ (r.created_at || '').slice(0, 16).replace('T', ' ') }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <PigletStockDetailPopup
      :visible="detail.visible"
      :code="detail.code"
      :name="detail.name"
      @close="detail.visible = false"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import BacktestForm from '../components/backtest/BacktestForm.vue'
import BacktestMetrics from '../components/backtest/BacktestMetrics.vue'
import BacktestTradesTable from '../components/backtest/BacktestTradesTable.vue'
import EquityCurveChart from '../components/backtest/EquityCurveChart.vue'
import PigletStockDetailPopup from '../components/strategy/PigletStockDetailPopup.vue'
import {
  fetchBacktest,
  fetchBacktests,
  runBacktest,
  runGridBacktest,
  type BacktestRequest,
  type BacktestResult,
  type BacktestRunInfo,
  type BacktestTradeItem,
  type EquityPoint,
} from '../api/client'

const tab = ref<'single' | 'grid' | 'history'>('single')

// ===== 单次回测 =====
const loading = ref(false)
const error = ref('')
const result = ref<BacktestResult | null>(null)

const drawdownCurve = computed<EquityPoint[]>(() => {
  if (!result.value?.equity_curve?.length) return []
  let peak = -Infinity
  return result.value.equity_curve.map((p) => {
    peak = Math.max(peak, p.total_value)
    const dd = peak > 0 ? (p.total_value / peak - 1) * 100 : 0
    return { date: p.date, cash: 0, market_value: 0, total_value: dd }
  })
})

async function pollBacktest(runId: number): Promise<BacktestResult> {
  return new Promise((resolve, reject) => {
    const interval = setInterval(async () => {
      try {
        const data = await fetchBacktest(runId)
        if (data.status === 'completed' || data.status === 'failed') {
          clearInterval(interval)
          if (data.status === 'failed') {
            reject(new Error(data.error_message || '回测失败'))
          } else {
            resolve(data)
          }
        }
      } catch (err: any) {
        clearInterval(interval)
        reject(err)
      }
    }, 1500)
  })
}

async function handleRunBacktest(req: BacktestRequest) {
  loading.value = true
  error.value = ''
  result.value = null
  try {
    const { run_id } = await runBacktest(req)
    result.value = await pollBacktest(run_id)
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err.message || '回测失败'
  } finally {
    loading.value = false
  }
}

async function loadRun(runId: number) {
  error.value = ''
  try {
    result.value = await fetchBacktest(runId)
    tab.value = 'single'
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载失败'
  }
}

// ===== 交易明细弹窗 =====
const detail = reactive({ visible: false, code: '', name: '' })

function onShowTradeDetail(t: BacktestTradeItem) {
  detail.code = t.stock_code
  detail.name = t.stock_name || t.stock_code
  detail.visible = true
}

// ===== 网格寻优 =====
const gridForm = reactive({
  start_date: fmt(dateDaysAgo(90)),
  end_date: fmt(new Date()),
  window_days: '3,5,8',
  hold_days: '3,5,10',
  max_positions: '5',
  max_per_day: '2',
  initial_capital: 100000,
})
const gridLoading = ref(false)
const gridError = ref('')
const gridResults = ref<BacktestRunInfo[]>([])
const gridDone = ref(0)
const gridTotal = ref(0)

function dateDaysAgo(n: number) {
  return new Date(Date.now() - n * 24 * 60 * 60 * 1000)
}

function fmt(d: Date) {
  return d.toISOString().split('T')[0]
}

function parseNumList(s: string): number[] {
  return s.split(/[,，\s]+/).map((x) => parseFloat(x)).filter((x) => !isNaN(x))
}

async function handleRunGrid() {
  gridError.value = ''
  const grid: Record<string, number[]> = {}
  for (const k of ['window_days', 'hold_days', 'max_positions', 'max_per_day'] as const) {
    const vals = parseNumList(gridForm[k])
    if (!vals.length) {
      gridError.value = `参数 ${k} 至少需要一个值`
      return
    }
    grid[k] = vals
  }
  const total = Object.values(grid).reduce((acc, v) => acc * v.length, 1)
  if (total > 24) {
    gridError.value = `参数组合 ${total} 个，超过上限 24`
    return
  }

  gridLoading.value = true
  gridResults.value = []
  gridDone.value = 0
  gridTotal.value = total
  try {
    const { run_ids } = await runGridBacktest({
      strategy_id: 'piglet',
      start_date: gridForm.start_date,
      end_date: gridForm.end_date,
      grid,
      base_params: { initial_capital: gridForm.initial_capital },
    })
    // 轮询直到全部完成
    await new Promise<void>((resolve) => {
      const timer = setInterval(async () => {
        const runs = (await fetchBacktests('piglet', 100)).filter((r) => run_ids.includes(r.id))
        gridDone.value = runs.filter((r) => r.status === 'completed' || r.status === 'failed').length
        gridResults.value = runs
        if (gridDone.value >= run_ids.length) {
          clearInterval(timer)
          resolve()
        }
      }, 2000)
    })
    // 按总收益降序
    gridResults.value.sort(
      (a, b) => (b.metrics?.total_return_pct ?? -Infinity) - (a.metrics?.total_return_pct ?? -Infinity)
    )
  } catch (err: any) {
    gridError.value = err?.response?.data?.detail || '寻优失败'
  } finally {
    gridLoading.value = false
  }
}

// ===== 历史记录 =====
const history = ref<BacktestRunInfo[]>([])

async function switchTab(t: 'single' | 'grid' | 'history') {
  tab.value = t
  if (t === 'history') {
    history.value = await fetchBacktests('piglet', 50)
  }
}

// ===== 展示工具 =====
function pctClass(v?: number | null) {
  if (v === null || v === undefined) return ''
  return v >= 0 ? 'up' : 'down'
}

function fmtPct(v?: number | null) {
  if (v === null || v === undefined) return '-'
  return v.toFixed(2) + '%'
}

function statusText(s: string) {
  return { completed: '完成', failed: '失败', running: '运行中', pending: '排队中' }[s] || s
}

function paramsText(p?: Record<string, any>) {
  if (!p) return '-'
  return `窗口${p.window_days} 持仓${p.hold_days} 仓位${p.max_positions} 日买${p.max_per_day}${p.require_dragon ? ' 游资' : ''}`
}
</script>

<style scoped>
.backtest-page {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.page-header h1 {
  font-size: 24px;
  font-weight: 600;
  color: #fff;
}

.tab-nav {
  display: flex;
  gap: 8px;
}

.tab-btn {
  padding: 7px 16px;
  border-radius: 6px;
  border: 1px solid #374151;
  background: #1f2937;
  color: #9ca3af;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.tab-btn.active {
  background: #2563eb;
  border-color: #2563eb;
  color: #fff;
}

.result-section {
  margin-top: 24px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.result-header,
.trades-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.result-header h2,
.chart-section h3,
.trades-header h3 {
  font-size: 16px;
  color: #e5e7eb;
  font-weight: 500;
  margin: 0;
}

.result-meta {
  font-size: 13px;
  color: #9ca3af;
}

.error-message {
  margin-top: 16px;
  padding: 12px 16px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 8px;
  color: #f87171;
  font-size: 14px;
}

.chart-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.trades-section {
  display: flex;
  flex-direction: column;
}

.panel {
  background: #1f2937;
  border-radius: 10px;
  padding: 18px;
  margin-bottom: 16px;
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: #d1d5db;
  margin-bottom: 14px;
}

.grid-form {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.grid-form .field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.grid-form label {
  font-size: 12px;
  color: #9ca3af;
}

.grid-form input {
  background: #111827;
  border: 1px solid #374151;
  border-radius: 6px;
  color: #e5e7eb;
  padding: 8px 10px;
  font-size: 13px;
  width: 140px;
}

.result-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.result-table th {
  text-align: left;
  padding: 8px 10px;
  color: #9ca3af;
  font-weight: 500;
  border-bottom: 1px solid #374151;
}

.result-table td {
  padding: 8px 10px;
  color: #e5e7eb;
  border-bottom: 1px solid #111827;
}

.result-table tr.clickable {
  cursor: pointer;
}

.result-table tr.clickable:hover {
  background: #111827;
}

.up { color: #ef4444; }
.down { color: #22c55e; }
.muted { color: #9ca3af; }

.btn-primary {
  padding: 8px 18px;
  border-radius: 6px;
  border: none;
  background: #2563eb;
  color: #fff;
  font-size: 13px;
  cursor: pointer;
}

.btn-primary:hover:not(:disabled) { background: #1d4ed8; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.empty {
  color: #6b7280;
  padding: 24px;
  text-align: center;
}
</style>
