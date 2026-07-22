<template>
  <div class="strategy-page">
    <header class="page-header">
      <h1>策略选股</h1>
    </header>

    <StrategyPicker
      :strategies="strategies"
      :selected-strategy="selectedStrategyId"
      :trade-date="tradeDate"
      :loading="loading"
      @update:selected-strategy="selectedStrategyId = $event"
      @update:trade-date="tradeDate = $event"
      @run="runStrategy"
    />

    <div class="result-section">
      <div class="result-header">
        <h2>选股结果</h2>
        <span v-if="result" class="result-meta">
          {{ result.trade_date }} · 共 {{ result.count }} 只
        </span>
      </div>

      <StrategyResultTable
        :items="result?.items || []"
        :strategy-id="result?.strategy_id || ''"
        @add-watchlist="addToWatchlist"
        @show-detail="openDetail"
      />

      <PigletStockDetailPopup
        :visible="detailPopup.visible"
        :code="detailPopup.code"
        :name="detailPopup.name"
        :industry="detailPopup.industry"
        @close="detailPopup.visible = false"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import StrategyPicker from '../components/strategy/StrategyPicker.vue'
import StrategyResultTable from '../components/strategy/StrategyResultTable.vue'
import PigletStockDetailPopup from '../components/strategy/PigletStockDetailPopup.vue'
import { fetchStrategies, fetchStrategyPicks, addToWatchlist as addToWatchlistApi } from '../api/client'
import type { StrategyInfo, StrategyPicksResponse, StrategyPickItem } from '../api/client'

const strategies = ref<StrategyInfo[]>([])
const selectedStrategyId = ref('')
const tradeDate = ref('')
const result = ref<StrategyPicksResponse | null>(null)
const loading = ref(false)
const detailPopup = ref({
  visible: false,
  code: '',
  name: '',
  industry: '',
})

function openDetail(item: StrategyPickItem) {
  detailPopup.value = {
    visible: true,
    code: item.code,
    name: item.name,
    industry: item.extra?.industry || '',
  }
}

async function loadStrategies() {
  try {
    strategies.value = await fetchStrategies()
    if (strategies.value.length > 0 && !selectedStrategyId.value) {
      selectedStrategyId.value = strategies.value[0].id
    }
  } catch (err: any) {
    alert(err?.response?.data?.detail || '加载策略列表失败')
  }
}

async function runStrategy() {
  if (!selectedStrategyId.value) return
  loading.value = true
  result.value = null
  try {
    result.value = await fetchStrategyPicks(
      selectedStrategyId.value,
      tradeDate.value || undefined,
    )
  } catch (err: any) {
    alert(err?.response?.data?.detail || '选股失败')
  } finally {
    loading.value = false
  }
}

async function addToWatchlist(code: string) {
  try {
    await addToWatchlistApi(code)
    alert(`已添加 ${code} 到自选`)
  } catch (err: any) {
    alert(err?.response?.data?.detail || '添加失败')
  }
}

onMounted(() => {
  loadStrategies()
})
</script>

<style scoped>
.strategy-page {
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
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.result-header h2 {
  font-size: 16px;
  color: #e5e7eb;
  font-weight: 500;
}

.result-meta {
  font-size: 13px;
  color: #9ca3af;
}
</style>
