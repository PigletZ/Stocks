<template>
  <div class="daily-tab">
    <section class="panel summary">
      <div class="panel-header"><h2>当日变化</h2><button :disabled="syncing" @click="syncData">{{ syncing ? '同步中…' : '同步所选日期' }}</button></div>
      <p v-if="!current">所选日期尚无收盘统计。可选择已有数据日期，或在收盘数据发布后同步。</p>
      <template v-else>
        <p v-for="line in summaryLines" :key="line">{{ line }}</p>
        <p v-if="!previous" class="muted">暂无更早统计，暂不计算变化。</p>
      </template>
      <p v-if="syncError" class="error" role="alert">{{ syncError }}</p>
      <p v-if="dashboard.status === 'partial'" class="notice">指数、市场广度或成交额尚未齐备。缺失指标显示 —，不会按零计算。</p>
    </section>

    <section class="metrics-grid" aria-label="市场核心指标">
      <article v-for="metric in metrics" :key="metric.label" class="metric-card">
        <div class="label">{{ metric.label }}</div>
        <strong :class="metric.tone">{{ metric.value }}</strong>
        <div class="comparison">{{ metric.comparison }}</div>
        <small>{{ metric.note }}</small>
      </article>
    </section>

    <section class="indices-grid" aria-label="主要指数">
      <div v-for="index in dashboard.indices" :key="index.code" class="index-card" @mouseenter="hoveredIndexCode = index.code" @mouseleave="hoveredIndexCode = ''">
        <span>{{ index.name }}</span><strong>{{ index.price.toFixed(2) }}</strong>
        <b :class="changeClass(index.change_pct)">{{ signed(index.change_pct) }}%</b>
        <IndexChartPopup v-if="hoveredIndexCode === index.code" :code="index.code" :name="index.name" :end-date="dashboard.date" />
      </div>
      <div v-if="!dashboard.indices.length" class="empty">所选日期暂无指数数据</div>
    </section>

    <section class="panel">
      <div class="panel-header"><div><h2>近期趋势</h2><small>截至 {{ dashboard.date }} · 按已有收盘记录展示，缺失指标留空</small></div>
        <div class="toggle"><button v-for="n in [20, 60]" :key="n" :class="{ active: range === n }" @click="range = n">近{{ n }}日</button></div>
      </div>
      <MarketTrendChart :history="dashboard.history" :range="range" />
    </section>

    <section class="panel">
      <div class="panel-header"><div><h2>短线结构</h2><small>仅在涨停明细与当日统计匹配时计算</small></div>
        <router-link :to="{ path: '/review/ladder', query: { date: dashboard.date } }">查看连板梯队 →</router-link>
      </div>
      <div class="structure-grid">
        <div><span>首板 / 二板 / 三板及以上</span><strong>{{ number(shortTerm.first_board) }} / {{ number(shortTerm.second_board) }} / {{ number(shortTerm.higher_board) }}</strong></div>
        <div><span>最高连板</span><strong>{{ number(shortTerm.max_board) }} <small>板</small></strong></div>
        <div><span>前次涨停今日平均涨幅</span><strong :class="changeClass(shortTerm.avg_pct)">{{ percent(shortTerm.avg_pct, true) }}</strong><small>有效报价 {{ shortTerm.quote_samples }} / {{ number(shortTerm.previous_count) }} 家</small></div>
        <div><span>前次涨停继续涨停</span><strong>{{ number(shortTerm.promoted) }} / {{ number(shortTerm.previous_count) }} <small>家</small></strong></div>
      </div>
      <div v-if="shortTerm.leaders.length" class="leaders"><span>最高板个股</span><router-link v-for="stock in shortTerm.leaders" :key="stock.code" :to="`/stock/${stock.code}`">{{ stock.name }} <small>{{ stock.code }}</small></router-link></div>
      <p v-if="!shortTerm.ready" class="notice">涨停明细尚未齐备，连板结构暂不计算。</p>
    </section>

    <section class="panel">
      <div class="panel-header"><div><h2>板块强弱</h2><small>排名变化对比 {{ previous?.date || '—' }}；成交量单位：手，不代表资金净流入</small></div>
        <div class="toggle"><button v-for="mode in sectorModes" :key="mode.key" :class="{ active: sectorMode === mode.key }" @click="sectorMode = mode.key">{{ mode.label }}</button></div>
      </div>
      <div class="sector-grid">
        <div v-for="group in sectorGroups" :key="group.label">
          <h3>{{ group.label }} <small>{{ group.rows.length }} 个</small></h3>
          <div class="sector-head"><span>板块 / 排名变化</span><span>{{ sectorMode === 'volume' ? '成交量' : '涨跌幅' }}</span></div>
          <div v-for="sector in group.rows.slice(0, expanded ? undefined : 8)" :key="sector.sector_code" class="sector-row">
            <div><span>{{ sector.sector_name }}</span><small>{{ rankText(sector.rank_change) }}</small></div>
            <strong v-if="sectorMode === 'volume'">{{ formatVolume(sector.volume) }}</strong>
            <strong v-else :class="changeClass(sector.change_pct)">{{ signed(sector.change_pct) }}%</strong>
          </div>
          <p v-if="!group.rows.length" class="empty">{{ dashboard.sectors.industry.length || dashboard.sectors.concept.length ? '暂无符合条件的板块' : '所选日期暂无板块数据' }}</p>
        </div>
      </div>
      <button class="expand" @click="expanded = !expanded">{{ expanded ? '收起列表' : '展开全部板块' }}</button>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import IndexChartPopup from '../IndexChartPopup.vue'
import MarketTrendChart from './MarketTrendChart.vue'
import { syncDailyOverview, syncReviewData, syncSectorRankingDaily } from '../../api/client'
import type { OverviewDashboard, DashboardSector } from '../../api/client'

const props = defineProps<{ dashboard: OverviewDashboard }>()
const emit = defineEmits<{ refresh: [] }>()
const current = computed(() => props.dashboard.current)
const previous = computed(() => props.dashboard.previous)
const shortTerm = computed(() => props.dashboard.short_term)
const range = ref(20)
const hoveredIndexCode = ref('')
const syncing = ref(false)
const syncError = ref('')
const expanded = ref(false)
const sectorMode = ref<'up' | 'down' | 'volume'>('up')
const sectorModes = [{ key: 'up' as const, label: '领涨' }, { key: 'down' as const, label: '领跌' }, { key: 'volume' as const, label: '成交量' }]

function number(value: number | null | undefined) { return value == null ? '—' : value.toLocaleString('zh-CN') }
function signed(value: number) { return `${value > 0 ? '+' : ''}${value.toFixed(2)}` }
function percent(value: number | null | undefined, withSign = false) { return value == null ? '—' : `${withSign ? signed(value) : value.toFixed(1)}%` }
function changeClass(value: number | null | undefined) { return value == null || value === 0 ? '' : value > 0 ? 'up' : 'down' }
function formatAmount(value: number | null | undefined) { return value == null ? '—' : value >= 1e12 ? `${(value / 1e12).toFixed(2)} 万亿` : `${(value / 1e8).toFixed(0)} 亿` }
function formatVolume(value: number) { return value >= 1e8 ? `${(value / 1e8).toFixed(2)} 亿手` : `${(value / 1e4).toFixed(1)} 万手` }
function delta(value: number | null | undefined, old: number | null | undefined, unit: string) {
  return value == null || old == null ? '暂无可比数据' : `较对比日 ${signed(value - old)}${unit}`
}
const turnoverChange = computed(() => {
  const now = current.value?.total_turnover, old = previous.value?.total_turnover
  return now == null || old == null || old <= 0 ? null : (now / old - 1) * 100
})
const metrics = computed(() => {
  const c = current.value, p = previous.value
  const avg = props.dashboard.turnover_average
  const avgNote = avg == null || c?.total_turnover == null ? '近期量能基准待补齐' : `相对前${props.dashboard.turnover_average_days}个有效交易日均量 ${signed((c.total_turnover / avg - 1) * 100)}%`
  return [
    { label: '上涨占比', value: percent(c?.up_ratio), comparison: delta(c?.up_ratio, p?.up_ratio, ' 个百分点'), note: `上涨 ${number(c?.up)} / 下跌 ${number(c?.down)} / 平盘 ${number(c?.flat)}`, tone: '' },
    { label: '全市场成交额', value: formatAmount(c?.total_turnover), comparison: turnoverChange.value == null ? '暂无可比数据' : `较对比日 ${signed(turnoverChange.value)}%`, note: avgNote, tone: '' },
    { label: '涨停家数', value: number(c?.limit_up), comparison: delta(c?.limit_up, p?.limit_up, ' 家'), note: '收盘涨停', tone: 'up' },
    { label: '跌停家数', value: number(c?.limit_down), comparison: delta(c?.limit_down, p?.limit_down, ' 家'), note: '收盘跌停', tone: 'down' },
    { label: '炸板率', value: percent(c?.break_rate), comparison: delta(c?.break_rate, p?.break_rate, ' 个百分点'), note: `炸板 ${number(c?.opened_limit)} /（涨停 + 炸板）`, tone: '' },
    { label: '涨停延续率', value: percent(shortTerm.value.promote_rate), comparison: `对比日涨停 ${number(shortTerm.value.previous_count)} 家`, note: '前次涨停股中，今日仍涨停的比例', tone: '' },
  ]
})
const summaryLines = computed(() => {
  const c = current.value, p = previous.value
  if (!c) return []
  const lines = []
  if (c.up_ratio != null) lines.push(`市场广度：${c.up_ratio.toFixed(1)}% 的交易股票上涨${p?.up_ratio != null ? `，较 ${p.date} ${c.up_ratio >= p.up_ratio ? '扩大' : '收窄'} ${Math.abs(c.up_ratio - p.up_ratio).toFixed(1)} 个百分点` : ''}。`)
  if (c.total_turnover != null) lines.push(`量能：成交 ${formatAmount(c.total_turnover)}${turnoverChange.value != null ? `，较对比日${turnoverChange.value >= 0 ? '增加' : '减少'} ${Math.abs(turnoverChange.value).toFixed(1)}%` : ''}。`)
  lines.push(`短线情绪：涨停 ${c.limit_up} 家、跌停 ${c.limit_down} 家${c.break_rate != null ? `，炸板率 ${c.break_rate.toFixed(1)}%` : ''}${p?.break_rate != null && c.break_rate != null ? `（较对比日${c.break_rate >= p.break_rate ? '上升' : '下降'} ${Math.abs(c.break_rate - p.break_rate).toFixed(1)} 个百分点）` : ''}。`)
  return lines
})
function sortSectors(rows: DashboardSector[]) {
  if (sectorMode.value === 'volume') return [...rows].sort((a, b) => b.volume - a.volume)
  return rows.filter(r => sectorMode.value === 'up' ? r.change_pct > 0 : r.change_pct < 0)
    .sort((a, b) => sectorMode.value === 'up' ? b.change_pct - a.change_pct : a.change_pct - b.change_pct)
}
const sectorGroups = computed(() => [
  { label: '行业板块', rows: sortSectors(props.dashboard.sectors.industry) },
  { label: '概念板块', rows: sortSectors(props.dashboard.sectors.concept) },
])
function rankText(value: number | null) { return value == null ? '暂无可比排名' : value === 0 ? '涨幅排名持平' : `涨幅排名${value > 0 ? '上升' : '下降'} ${Math.abs(value)} 位` }
async function syncData() {
  syncing.value = true
  syncError.value = ''
  const date = props.dashboard.date
  const results = await Promise.allSettled([syncDailyOverview(date), syncReviewData(date), syncSectorRankingDaily(date)])
  syncing.value = false
  if (results.some(r => r.status === 'rejected')) syncError.value = '部分数据同步失败，请稍后重试；刷新可查看已入库部分。'
  else emit('refresh')
}
</script>

<style scoped>
.daily-tab { display:flex; flex-direction:column; gap:24px; }
.panel { background:#111827; border:1px solid #253045; border-radius:12px; padding:24px; }
.panel-header { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px; margin-bottom:16px; }
h2 { margin:0 0 6px; font-size:16px; color:#e5e7eb; } h3 { font-size:14px; font-weight:500; }
p { color:#d1d5db; font-size:14px; line-height:1.8; margin:6px 0; }
small,.muted { color:#9ca3af; font-size:12px; font-weight:400; }
button { border:1px solid #374151; border-radius:6px; padding:6px 12px; color:#d1d5db; background:#111827; cursor:pointer; }
button:disabled { opacity:.5; } .toggle { display:flex; gap:6px; } .toggle .active { background:#2563eb; border-color:#2563eb; color:white; }
a { color:#60a5fa; text-decoration:none; font-size:13px; } a:hover { color:#93c5fd; }
.summary { border-left:3px solid #60a5fa; background:linear-gradient(110deg,#152239,#111827 75%); }.summary p { line-height:1.9; font-size:14px; }
.metrics-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; }
.metric-card { background:linear-gradient(160deg,#162033,#111827); border:1px solid #253045; border-radius:10px; padding:20px 18px; }
.label,.comparison { color:#9ca3af; font-size:12px; }
.metric-card strong { display:block; color:#fff; font-size:28px; letter-spacing:-.5px; margin:16px 0; }
.metric-card small { display:block; margin-top:8px; line-height:1.6; }
.comparison { color:#d1d5db; }
.indices-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; }
.index-card { background:#111827; padding:14px; border-radius:8px; position:relative; display:flex; flex-wrap:wrap; gap:8px 14px; align-items:baseline; }
.index-card>span { width:100%; color:#9ca3af; font-size:12px; }.index-card>strong { font-size:20px; color:#e5e7eb; }.index-card>b { font-size:13px; }
.index-card :deep(.index-chart-popup) { position:absolute; top:100%; left:0; z-index:20; }
.structure-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:16px; }
.structure-grid>div { background:#111827; padding:16px; border-radius:6px; }.structure-grid span { color:#9ca3af; font-size:12px; }.structure-grid strong { display:block; margin:12px 0; font-size:22px; color:#e5e7eb; }
.leaders { display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin-top:16px; font-size:12px; color:#9ca3af; }.leaders a { padding:6px 10px; background:#111827; border-radius:4px; }
.sector-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:24px; }.sector-head,.sector-row { display:flex; justify-content:space-between; gap:16px; padding:10px 12px; font-size:13px; }.sector-head { color:#9ca3af; font-size:12px; }.sector-row { background:#111827; border-radius:6px; margin-bottom:6px; align-items:center; }.sector-row span { color:#e5e7eb; }.sector-row small { display:block; margin-top:5px; }.sector-row strong { white-space:nowrap; font-size:14px; }
.expand { display:block; margin:16px auto 0; }.empty { text-align:center; padding:24px; color:#9ca3af; font-size:13px; }.notice { color:#fbbf24; font-size:12px; }.error { color:#fca5a5; }
.up,.metric-card strong.up,.structure-grid strong.up { color:#ef4444; }.down,.metric-card strong.down,.structure-grid strong.down { color:#22c55e; }
@media(max-width:800px) { .sector-grid { grid-template-columns:1fr; }.metrics-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }.panel { padding:16px; } }
</style>
