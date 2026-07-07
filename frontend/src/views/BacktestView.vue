<template>
  <div class="backtest-page">
    <header class="page-header">
      <h1>策略回测</h1>
    </header>

    <BacktestForm :loading="loading" @run="handleRunBacktest" />

    <div v-if="error" class="error-message">{{ error }}</div>

    <div v-if="result" class="result-section">
      <div class="result-header">
        <h2>回测结果</h2>
        <span class="result-meta">
          {{ result.start_date }} ~ {{ result.end_date }} · {{ result.status === 'completed' ? '完成' : result.status }}
        </span>
      </div>

      <BacktestMetrics :metrics="result.metrics" />

      <div class="chart-section">
        <h3>权益曲线</h3>
        <EquityCurveChart :equity-curve="result.equity_curve" />
      </div>

      <div class="trades-section">
        <div class="trades-header">
          <h3>交易明细</h3>
          <span class="result-meta">共 {{ (result.trades || []).length }} 笔</span>
        </div>
        <BacktestTradesTable :trades="result.trades || []" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import BacktestForm from '../components/backtest/BacktestForm.vue'
import BacktestMetrics from '../components/backtest/BacktestMetrics.vue'
import BacktestTradesTable from '../components/backtest/BacktestTradesTable.vue'
import EquityCurveChart from '../components/backtest/EquityCurveChart.vue'
import { runBacktest, fetchBacktest } from '../api/client'
import type { BacktestRequest, BacktestResult } from '../api/client'

const loading = ref(false)
const error = ref('')
const result = ref<BacktestResult | null>(null)

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
</script>

<style scoped>
.backtest-page {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h1 {
  font-size: 24px;
  font-weight: 600;
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
</style>
