<template>
  <div class="page">
    <div class="page-header">
      <h1>连板梯队</h1>
      <div class="actions">
        <input type="date" v-model="selectedDate" @change="loadAll" />
        <button class="btn-secondary" @click="onSync" :disabled="syncing">
          {{ syncing ? '同步中...' : '同步当日数据' }}
        </button>
      </div>
    </div>

    <div v-if="error" class="error-message">{{ error }}</div>
    <div v-if="loading" class="loading-text">加载中...</div>

    <template v-else>
      <p v-if="perf.ready === false" class="loading-text">当日或对比日明细尚未齐备，延续率不计算；缺失报价标为未知。</p>
      <!-- 昨日涨停表现统计 -->
      <div v-if="perf.stats.total" class="stats-row">
        <div class="stat-card">
          <div class="stat-label">{{ perf.prev_date }} 涨停</div>
          <div class="stat-value">{{ perf.stats.total }} 家</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">晋级率</div>
          <div class="stat-value" :class="(perf.stats.promote_rate ?? 0) >= 30 ? 'up' : ''">
            {{ perf.stats.promote_rate == null ? '—' : perf.stats.promote_rate + '%' }}
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-label">平均涨幅</div>
          <div class="stat-value" :class="changeClass(perf.stats.avg_pct)">
            {{ perf.stats.avg_pct !== null ? perf.stats.avg_pct + '%' : '-' }}
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-label">晋级 / 炸板 / 跌停</div>
          <div class="stat-value">
            <span class="up">{{ perf.stats.promoted ?? '—' }}</span> /
            <span class="warn">{{ perf.stats.opened ?? '—' }}</span> /
            <span class="down">{{ perf.stats.limit_down ?? '—' }}</span>
          </div>
        </div>
      </div>

      <!-- 梯队图 -->
      <div class="panel">
        <div class="panel-title">
          {{ ladder.trade_date }} 涨停梯队（共 {{ ladder.total }} 家）
        </div>
        <div v-if="!ladder.ladder.length" class="empty">暂无数据</div>
        <div v-else class="ladder">
          <div v-for="group in ladder.ladder" :key="group.boards" class="ladder-col">
            <div class="ladder-head" :class="{ high: group.boards >= 3 }">
              {{ group.boards }} 板 <span class="count">x{{ group.count }}</span>
            </div>
            <div
              v-for="s in group.stocks"
              :key="s.code"
              class="stock-chip"
              @click="openDetail(s.code, s.name)"
            >
              <div class="chip-name">{{ s.name }}</div>
              <div class="chip-meta">
                <span v-if="s.first_time" class="time">{{ formatTime(s.first_time) }}</span>
                <span v-if="s.open_times" class="open-times">开{{ s.open_times }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 昨日涨停今日表现明细 -->
      <div v-if="perf.items.length" class="panel">
        <div class="panel-title">昨日涨停今日表现（{{ perf.trade_date }}）</div>
        <table class="result-table">
          <thead>
            <tr>
              <th>代码</th>
              <th>名称</th>
              <th>昨日连板</th>
              <th>今日涨幅</th>
              <th>今日状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in perf.items" :key="item.code" @click="openDetail(item.code, item.name)">
              <td class="code">{{ item.code }}</td>
              <td>{{ item.name }}</td>
              <td>{{ item.prev_boards }} 板</td>
              <td :class="changeClass(item.today_pct)">
                {{ item.today_pct !== null ? item.today_pct + '%' : '-' }}
              </td>
              <td>
                <span class="status-tag" :class="statusClass(item.status)">
                  {{ item.status }}<template v-if="item.status === '晋级' && item.today_boards">{{ item.today_boards }}板</template>
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <PigletStockDetailPopup
      :visible="detail.visible"
      :code="detail.code"
      :name="detail.name"
      :as-of="selectedDate || ladder.trade_date || undefined"
      @close="detail.visible = false"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  fetchLimitLadder,
  fetchLimitPerformance,
  syncReviewData,
  type LimitLadderResponse,
  type LimitPerfResponse,
} from '../api/client'
import PigletStockDetailPopup from '../components/strategy/PigletStockDetailPopup.vue'

const route = useRoute()
const selectedDate = ref(typeof route.query.date === 'string' ? route.query.date : '')
const loading = ref(false)
const syncing = ref(false)
const error = ref('')
const ladder = ref<LimitLadderResponse>({ trade_date: null, ladder: [], total: 0 })
const perf = ref<LimitPerfResponse>({ trade_date: null, prev_date: null, stats: { total: 0, promoted: 0, promote_rate: 0, opened: 0, limit_down: 0, avg_pct: null }, items: [] })
const detail = reactive({ visible: false, code: '', name: '' })

function changeClass(n: number | null | undefined) {
  if (n === null || n === undefined) return ''
  return n >= 0 ? 'up' : 'down'
}

function statusClass(s: string) {
  return { 'tag-up': s === '晋级', 'tag-warn': s === '炸板', 'tag-down': s === '跌停', 'tag-flat': s === '红盘' || s === '绿盘' }
}

function formatTime(t: string) {
  const s = t.padStart(6, '0')
  return `${s.slice(0, 2)}:${s.slice(2, 4)}`
}

function openDetail(code: string, name: string) {
  detail.code = code
  detail.name = name
  detail.visible = true
}

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    const d = selectedDate.value || undefined
    const [l, p] = await Promise.all([fetchLimitLadder(d), fetchLimitPerformance(d)])
    ladder.value = l
    perf.value = p
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

async function onSync() {
  syncing.value = true
  error.value = ''
  try {
    await syncReviewData(selectedDate.value || undefined)
    await loadAll()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '同步失败'
  } finally {
    syncing.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.page {
  padding: 20px;
  max-width: 1400px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.page-header h1 {
  font-size: 20px;
  color: #e5e7eb;
}

.actions {
  display: flex;
  gap: 10px;
  align-items: center;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.stat-card {
  background: #1f2937;
  border-radius: 10px;
  padding: 14px 18px;
}

.stat-label {
  font-size: 12px;
  color: #9ca3af;
  margin-bottom: 6px;
}

.stat-value {
  font-size: 20px;
  font-weight: 600;
  color: #e5e7eb;
}

.up { color: #ef4444; }
.down { color: #22c55e; }
.warn { color: #f59e0b; }

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

.ladder {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  overflow-x: auto;
  padding-bottom: 4px;
}

.ladder-col {
  min-width: 140px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ladder-head {
  font-size: 13px;
  font-weight: 600;
  color: #9ca3af;
  padding: 6px 10px;
  background: #111827;
  border-radius: 6px;
  text-align: center;
}

.ladder-head.high {
  color: #ef4444;
}

.ladder-head .count {
  color: #6b7280;
  font-weight: 400;
}

.stock-chip {
  background: #111827;
  border: 1px solid #374151;
  border-radius: 6px;
  padding: 8px 10px;
  cursor: pointer;
  transition: border-color 0.2s;
}

.stock-chip:hover {
  border-color: #60a5fa;
}

.chip-name {
  font-size: 13px;
  color: #e5e7eb;
  margin-bottom: 4px;
}

.chip-meta {
  display: flex;
  gap: 8px;
  font-size: 11px;
  color: #6b7280;
}

.chip-meta .open-times {
  color: #f59e0b;
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
  border-bottom: 1px solid #1f2937;
}

.result-table tbody tr {
  cursor: pointer;
}

.result-table tbody tr:hover {
  background: #111827;
}

.result-table .code {
  color: #9ca3af;
}

.status-tag {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.tag-up { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
.tag-warn { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
.tag-down { background: rgba(34, 197, 94, 0.15); color: #22c55e; }
.tag-flat { background: #374151; color: #9ca3af; }

.loading-text {
  color: #9ca3af;
  padding: 40px;
  text-align: center;
}

.empty {
  color: #6b7280;
  padding: 24px;
  text-align: center;
}

.error-message {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.4);
  color: #ef4444;
  border-radius: 8px;
  padding: 10px 14px;
  margin-bottom: 16px;
}

.btn-secondary {
  padding: 8px 14px;
  border-radius: 6px;
  border: 1px solid #374151;
  background: #1f2937;
  color: #d1d5db;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-secondary:hover:not(:disabled) {
  border-color: #60a5fa;
  color: #60a5fa;
}

.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
