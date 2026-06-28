<template>
  <div class="realtime-tab">
    <!-- 涨跌排行 -->
    <section class="ranking-section">
      <div class="section-title">涨跌排行</div>
      <div class="movers-grid">
        <section class="panel">
          <div class="panel-header">
            <h2>实时涨幅榜</h2>
            <span v-if="loading" class="loading-text">加载中...</span>
          </div>
          <div v-if="data.top_gainers.length > 0" class="stock-list">
            <router-link
              v-for="stock in data.top_gainers"
              :key="stock.代码"
              :to="`/stock/${stock.代码}`"
              class="stock-item"
            >
              <div class="stock-main">
                <span class="stock-code">{{ stock.代码 }}</span>
                <span class="stock-name">{{ stock.名称 }}</span>
              </div>
              <span class="stock-change up">+{{ stock.涨跌幅.toFixed(2) }}%</span>
            </router-link>
          </div>
          <div v-else-if="!loading" class="empty">暂无数据</div>
        </section>

        <section class="panel">
          <div class="panel-header">
            <h2>实时跌幅榜</h2>
            <span v-if="loading" class="loading-text">加载中...</span>
          </div>
          <div v-if="data.top_losers.length > 0" class="stock-list">
            <router-link
              v-for="stock in data.top_losers"
              :key="stock.代码"
              :to="`/stock/${stock.代码}`"
              class="stock-item"
            >
              <div class="stock-main">
                <span class="stock-code">{{ stock.代码 }}</span>
                <span class="stock-name">{{ stock.名称 }}</span>
              </div>
              <span class="stock-change down">{{ stock.涨跌幅.toFixed(2) }}%</span>
            </router-link>
          </div>
          <div v-else-if="!loading" class="empty">暂无数据</div>
        </section>
      </div>
    </section>

    <!-- 板块排行 -->
    <section class="ranking-section">
      <div class="section-title">板块排行</div>
      <div class="movers-grid">
        <section class="panel">
          <div class="panel-header">
            <h2>行业板块涨幅</h2>
            <span v-if="sectorsLoading" class="loading-text">加载中...</span>
          </div>
          <div v-if="industrySectors.length > 0" class="stock-list">
            <div
              v-for="sector in industrySectors"
              :key="sector.sector_code"
              class="stock-item"
            >
              <div class="stock-main">
                <span class="stock-code">{{ sector.sector_name }}</span>
                <span class="stock-name">{{ formatAmount(sector.volume) }}</span>
              </div>
              <span class="stock-change" :class="changeClass(sector.change_pct)">
                {{ formatChange(sector.change_pct) }}
              </span>
            </div>
          </div>
          <div v-else-if="!sectorsLoading" class="empty">暂无数据</div>
        </section>

        <section class="panel">
          <div class="panel-header">
            <h2>概念板块涨幅</h2>
            <span v-if="sectorsLoading" class="loading-text">加载中...</span>
          </div>
          <div v-if="conceptSectors.length > 0" class="stock-list">
            <div
              v-for="sector in conceptSectors"
              :key="sector.sector_code"
              class="stock-item"
            >
              <div class="stock-main">
                <span class="stock-code">{{ sector.sector_name }}</span>
                <span class="stock-name">{{ formatAmount(sector.volume) }}</span>
              </div>
              <span class="stock-change" :class="changeClass(sector.change_pct)">
                {{ formatChange(sector.change_pct) }}
              </span>
            </div>
          </div>
          <div v-else-if="!sectorsLoading" class="empty">暂无数据</div>
        </section>
      </div>
    </section>

    <!-- 涨速榜 -->
    <section class="ranking-section">
      <div class="section-title">涨速榜</div>
      <div class="speed-toggle">
        <button
          v-for="opt in speedOptions"
          :key="opt.key"
          class="toggle-btn"
          :class="{ active: speedInterval === opt.key }"
          @click="speedInterval = opt.key"
        >
          {{ opt.label }}
        </button>
      </div>
      <div class="movers-grid">
        <section class="panel">
          <div class="panel-header">
            <h2>{{ speedTitle }}快速拉升</h2>
            <span v-if="speedLoading" class="loading-text">加载中...</span>
          </div>
          <div v-if="speedUpList.length > 0" class="stock-list">
            <router-link
              v-for="stock in speedUpList"
              :key="stock.代码"
              :to="`/stock/${stock.代码}`"
              class="stock-item"
            >
              <div class="stock-main">
                <span class="stock-code">{{ stock.代码 }}</span>
                <span class="stock-name">{{ stock.名称 }}</span>
              </div>
              <div class="stock-extra">
                <span class="stock-change up">+{{ stock.speed_value.toFixed(2) }}%</span>
                <span class="stock-total">{{ stock.涨跌幅.toFixed(2) }}%</span>
              </div>
            </router-link>
          </div>
          <div v-else-if="!speedLoading" class="empty">暂无数据</div>
        </section>

        <section class="panel">
          <div class="panel-header">
            <h2>{{ speedTitle }}快速下跌</h2>
            <span v-if="speedLoading" class="loading-text">加载中...</span>
          </div>
          <div v-if="speedDownList.length > 0" class="stock-list">
            <router-link
              v-for="stock in speedDownList"
              :key="stock.代码"
              :to="`/stock/${stock.代码}`"
              class="stock-item"
            >
              <div class="stock-main">
                <span class="stock-code">{{ stock.代码 }}</span>
                <span class="stock-name">{{ stock.名称 }}</span>
              </div>
              <div class="stock-extra">
                <span class="stock-change down">{{ stock.speed_value.toFixed(2) }}%</span>
                <span class="stock-total">{{ stock.涨跌幅.toFixed(2) }}%</span>
              </div>
            </router-link>
          </div>
          <div v-else-if="!speedLoading" class="empty">暂无数据</div>
        </section>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { fetchSectorRanking, fetchSpeedRanking } from '../../api/client'
import type { RealtimeOverview, SectorDailyItem, SpeedRankingItem } from '../../api/client'

defineProps<{
  data: RealtimeOverview
  loading: boolean
}>()

const speedInterval = ref<'5min' | '15min'>('5min')

const sectorsLoading = ref(false)
const speedLoading = ref(false)
const industrySectors = ref<SectorDailyItem[]>([])
const conceptSectors = ref<SectorDailyItem[]>([])
const speed5minUp = ref<SpeedRankingItem[]>([])
const speed5minDown = ref<SpeedRankingItem[]>([])
const speed15minUp = ref<SpeedRankingItem[]>([])
const speed15minDown = ref<SpeedRankingItem[]>([])

const speedOptions: { key: '5min' | '15min'; label: string }[] = [
  { key: '5min', label: '5分钟' },
  { key: '15min', label: '15分钟' },
]

const speedTitle = computed(() => {
  return speedInterval.value === '5min' ? '5分钟' : '15分钟'
})

const speedUpList = computed<SpeedRankingItem[]>(() => {
  return speedInterval.value === '5min'
    ? speed5minUp.value
    : speed15minUp.value
})

const speedDownList = computed<SpeedRankingItem[]>(() => {
  return speedInterval.value === '5min'
    ? speed5minDown.value
    : speed15minDown.value
})

async function loadSectors() {
  if (industrySectors.value.length && conceptSectors.value.length) return
  sectorsLoading.value = true
  try {
    const [industry, concept] = await Promise.all([
      fetchSectorRanking('industry', 10),
      fetchSectorRanking('concept', 10),
    ])
    industrySectors.value = industry
    conceptSectors.value = concept
  } catch (err) {
    console.error('Failed to load sectors', err)
  } finally {
    sectorsLoading.value = false
  }
}

async function loadSpeed() {
  if (speed5minUp.value.length) return
  speedLoading.value = true
  try {
    const [up5, down5, up15, down15] = await Promise.all([
      fetchSpeedRanking('5min', 'up', 10),
      fetchSpeedRanking('5min', 'down', 10),
      fetchSpeedRanking('15min', 'up', 10),
      fetchSpeedRanking('15min', 'down', 10),
    ])
    speed5minUp.value = up5
    speed5minDown.value = down5
    speed15minUp.value = up15
    speed15minDown.value = down15
  } catch (err) {
    console.error('Failed to load speed ranking', err)
  } finally {
    speedLoading.value = false
  }
}

onMounted(() => {
  loadSectors()
  loadSpeed()
})

function changeClass(value: number): string {
  if (value > 0) return 'up'
  if (value < 0) return 'down'
  return ''
}

function formatChange(value: number): string {
  const prefix = value > 0 ? '+' : ''
  return `${prefix}${value.toFixed(2)}%`
}

function formatAmount(amount: number): string {
  if (amount >= 1e8) {
    return (amount / 1e8).toFixed(2) + '亿'
  }
  if (amount >= 1e4) {
    return (amount / 1e4).toFixed(2) + '万'
  }
  return amount.toFixed(0)
}
</script>

<style scoped>
.realtime-tab {
  display: flex;
  flex-direction: column;
  gap: 28px;
}

.ranking-section {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.section-title {
  font-size: 17px;
  font-weight: 600;
  color: #e5e7eb;
  padding-left: 4px;
}

.movers-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  gap: 20px;
}

.panel {
  background: #1f2937;
  border-radius: 10px;
  padding: 18px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}

.panel-header h2 {
  font-size: 16px;
  font-weight: 600;
  color: #e5e7eb;
  margin: 0;
}

.loading-text {
  font-size: 13px;
  color: #6b7280;
}

.stock-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stock-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-radius: 6px;
  background: #111827;
  text-decoration: none;
  transition: background 0.2s;
}

.stock-item:hover {
  background: #1a2230;
}

.stock-main {
  display: flex;
  gap: 10px;
  align-items: center;
  min-width: 0;
}

.stock-code {
  font-weight: 600;
  color: #fff;
  font-size: 14px;
  min-width: 70px;
}

.stock-name {
  color: #9ca3af;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.stock-extra {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
}

.stock-change {
  font-size: 13px;
  font-weight: 600;
}

.stock-change.up {
  color: #ef4444;
}

.stock-change.down {
  color: #22c55e;
}

.stock-total {
  font-size: 12px;
  color: #6b7280;
}

.empty {
  color: #6b7280;
  font-size: 13px;
  text-align: center;
  padding: 30px 0;
}

.speed-toggle {
  display: flex;
  gap: 8px;
}

.toggle-btn {
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid #374151;
  background: #111827;
  color: #9ca3af;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.toggle-btn:hover {
  background: #1f2937;
  color: #e5e7eb;
}

.toggle-btn.active {
  background: #2563eb;
  color: #fff;
  border-color: #2563eb;
}
</style>
