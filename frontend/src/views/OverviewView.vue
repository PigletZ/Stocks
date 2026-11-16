<template>
  <div class="overview">
    <header class="page-header">
      <div class="heading"><span class="eyebrow">收盘复盘 / 全市场</span><h1>市场全景<span class="heading-dot"></span></h1><p>看清变化，追踪强弱</p></div>
      <div class="date-controls">
        <button :disabled="!previousDate || loading" @click="changeDate(previousDate)">◀ 前一日</button>
        <input aria-label="复盘交易日期" type="date" :value="selectedDate" :max="today" @change="onDateInput" />
        <button :disabled="!nextDate || loading" @click="changeDate(nextDate)">后一日 ▶</button>
        <button @click="loadDashboard()" :disabled="loading">最新收盘</button>
        <button @click="loadDashboard(selectedDate)" :disabled="loading">刷新</button>
      </div>
    </header>
    <div class="data-status" aria-live="polite">
      <span class="badge" :class="dashboard?.status">{{ loading ? '加载中…' : statusText }}</span>
      <span>数据日期 {{ selectedDate || '—' }} · 收盘数据</span>
      <span>统计同步于 {{ updatedText }}</span>
      <span v-if="dashboard?.previous">对比 {{ dashboard.previous.date }}</span>
    </div>
    <div v-if="error" class="error" role="alert">{{ error }} <button @click="loadDashboard(selectedDate)">重试</button></div>
    <nav class="tab-nav" aria-label="概览分类">
      <button v-for="tab in tabs" :key="tab.key" :class="{ active: activeTab === tab.key }" @click="activeTab = tab.key">{{ tab.label }}</button>
    </nav>
    <div v-if="loading" class="loading-panel">正在整理市场数据…</div>
    <div v-else-if="dashboard" :key="selectedDate">
      <DailyTab v-if="activeTab === 'daily'" :dashboard="dashboard" @refresh="loadDashboard(selectedDate)" />
      <LimitTab v-if="activeTab === 'limit-up'" title="涨停股票" type="up" :trade-date="selectedDate" @add-watchlist="addToWl" />
      <LimitTab v-if="activeTab === 'limit-down'" title="跌停股票" type="down" :trade-date="selectedDate" @add-watchlist="addToWl" />
      <DragonTigerTab v-if="activeTab === 'dragon-tiger'" :trade-date="selectedDate" @add-watchlist="addToWl" />
      <TopGainersTab v-if="activeTab === 'top-gainers'" :trade-date="selectedDate" @add-watchlist="addToWl" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import DailyTab from '../components/overview/DailyTab.vue'
import LimitTab from '../components/overview/LimitTab.vue'
import DragonTigerTab from '../components/overview/DragonTigerTab.vue'
import TopGainersTab from '../components/overview/TopGainersTab.vue'
import { fetchOverviewDashboard, addToWatchlist } from '../api/client'
import type { OverviewDashboard } from '../api/client'

const route = useRoute()
const selectedDate = ref('')
const dashboard = ref<OverviewDashboard | null>(null)
const activeTab = ref('daily')
const loading = ref(false)
const error = ref('')
let controller: AbortController | null = null
const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date())
const tabs = [
  { key: 'daily', label: '日概览' }, { key: 'limit-up', label: '涨停' },
  { key: 'limit-down', label: '跌停' }, { key: 'dragon-tiger', label: '龙虎榜' },
  { key: 'top-gainers', label: '涨幅榜' },
]
const previousDate = computed(() => [...(dashboard.value?.available_dates || [])].reverse().find(d => d < selectedDate.value) || '')
const nextDate = computed(() => dashboard.value?.available_dates.find(d => d > selectedDate.value) || '')
const statusText = computed(() => ({ ready: '统计已就绪', partial: '部分数据待补齐', missing: '所选日期暂无统计' })[dashboard.value?.status || 'missing'])
const updatedText = computed(() => dashboard.value?.updated_at
  ? new Date(dashboard.value.updated_at).toLocaleString('zh-CN', { hour12: false }) : '—')

async function loadDashboard(date?: string) {
  controller?.abort()
  const request = new AbortController()
  controller = request
  loading.value = true
  error.value = ''
  try {
    const data = await fetchOverviewDashboard(date || undefined, request.signal)
    if (request.signal.aborted) return
    dashboard.value = data
    selectedDate.value = data.date
  } catch (err: any) {
    if (!request.signal.aborted) error.value = err?.response?.data?.detail || '加载失败，请重试。'
  } finally {
    if (controller === request) loading.value = false
  }
}
function changeDate(date: string) { if (date) loadDashboard(date) }
function onDateInput(event: Event) { changeDate((event.target as HTMLInputElement).value) }
async function addToWl(code: string) {
  try { await addToWatchlist(code); alert(`已添加 ${code} 到自选`) }
  catch (err: any) { alert(err?.response?.data?.detail || '添加失败') }
}
onMounted(() => {
  const initialDate = typeof route.query.date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(route.query.date) ? route.query.date : undefined
  loadDashboard(initialDate)
})
onUnmounted(() => controller?.abort())
</script>

<style scoped>
.overview { padding:32px; max-width:1560px; margin:0 auto; font-variant-numeric:tabular-nums; }
.page-header { display:flex; justify-content:space-between; align-items:center; gap:16px; flex-wrap:wrap; }
h1 { margin:6px 0 0; font-size:30px; letter-spacing:1px; color:#fff; display:flex; align-items:center; gap:12px; }
.eyebrow { color:#60a5fa; font-size:11px; letter-spacing:2px; }.heading-dot { height:7px; width:7px; border-radius:50%; background:#60a5fa; box-shadow:0 0 18px #2563eb; }
p { color:#9ca3af; font-size:13px; margin:8px 0 0; }
.date-controls,.data-status,.tab-nav { display:flex; align-items:center; flex-wrap:wrap; gap:10px; }
button,input { padding:7px 12px; border:1px solid #374151; border-radius:6px; background:#111827; color:#d1d5db; cursor:pointer; }
button:disabled { opacity:.4; cursor:default; }
.data-status { margin:24px 0 18px; padding:14px 0; border-top:1px solid #1f2937; border-bottom:1px solid #1f2937; color:#9ca3af; font-size:12px; gap:16px; }
.badge { padding:4px 8px; background:#1f2937; border-radius:4px; color:#fbbf24; }
.badge.ready { color:#93c5fd; background:#172554; }
.tab-nav { padding:5px; margin-bottom:24px; background:#111827; border-radius:8px; width:fit-content; }
.tab-nav button { background:transparent; border-color:transparent; }
.tab-nav .active { background:#2563eb; color:white; }
.error { background:#7f1d1d; color:#fecaca; padding:12px; border-radius:6px; margin-bottom:16px; }
.loading-panel { padding:64px; text-align:center; color:#9ca3af; }
@media(max-width:600px) { .overview { padding:16px; } .date-controls { gap:6px; } button,input { padding:7px 8px; } }
</style>
