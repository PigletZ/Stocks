<template>
  <div class="page">
    <div class="page-header">
      <h1>复盘日志</h1>
      <div class="tab-nav">
        <button class="tab-btn" :class="{ active: tab === 'note' }" @click="tab = 'note'">复盘笔记</button>
        <button class="tab-btn" :class="{ active: tab === 'trades' }" @click="switchTab('trades')">交易台账</button>
        <button class="tab-btn" :class="{ active: tab === 'positions' }" @click="switchTab('positions')">当前持仓</button>
      </div>
    </div>

    <!-- 统计卡 -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-label">已实现盈亏</div>
        <div class="stat-value" :class="changeClass(stats.total_realized)">{{ fmtMoney(stats.total_realized) }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">胜率（{{ stats.win_count }}胜 / {{ stats.loss_count }}负）</div>
        <div class="stat-value">{{ stats.win_rate !== null ? stats.win_rate + '%' : '-' }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">买入 / 卖出次数</div>
        <div class="stat-value">{{ stats.buy_count }} / {{ stats.sell_count }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">累计费用</div>
        <div class="stat-value">{{ fmtMoney(stats.total_fee) }}</div>
      </div>
    </div>

    <!-- 复盘笔记 -->
    <div v-show="tab === 'note'" class="note-layout">
      <div class="panel calendar-panel">
        <div class="cal-head">
          <button class="btn-link" @click="shiftMonth(-1)">‹</button>
          <span>{{ calYear }} 年 {{ calMonth }} 月</span>
          <button class="btn-link" @click="shiftMonth(1)">›</button>
        </div>
        <div class="cal-grid">
          <div v-for="w in ['一','二','三','四','五','六','日']" :key="w" class="cal-week">{{ w }}</div>
          <div
            v-for="cell in calendarCells"
            :key="cell.key"
            class="cal-cell"
            :class="{ other: !cell.inMonth, today: cell.isToday, selected: cell.date === selectedDate }"
            @click="selectDate(cell.date)"
          >
            <span>{{ cell.day }}</span>
            <span class="dots">
              <i v-if="cell.hasNote" class="dot note-dot"></i>
              <i v-if="cell.hasTrade" class="dot trade-dot"></i>
            </span>
          </div>
        </div>
        <div class="cal-legend">
          <span><i class="dot note-dot"></i> 有笔记</span>
          <span><i class="dot trade-dot"></i> 有交易</span>
        </div>
      </div>

      <div class="panel editor-panel">
        <div class="panel-title">{{ selectedDate }} 复盘笔记</div>
        <textarea
          v-model="noteContent"
          class="note-editor"
          placeholder="今日市场总结、操作回顾、明日计划..."
          rows="12"
        ></textarea>
        <input v-model="noteCodes" class="codes-input" placeholder="关联股票代码，逗号分隔（如 000001,600519）" />
        <div class="editor-actions">
          <button class="btn-primary" @click="onSaveNote" :disabled="saving">{{ saving ? '保存中...' : '保存' }}</button>
          <button class="btn-link danger" @click="onDeleteNote" v-if="noteExists">删除</button>
          <span v-if="savedTip" class="saved-tip">已保存</span>
        </div>
        <div v-if="dayTrades.length" class="day-trades">
          <div class="panel-title">当日交易</div>
          <div v-for="t in dayTrades" :key="t.id" class="day-trade-item">
            <span class="status-tag" :class="t.direction === 'buy' ? 'tag-up' : 'tag-down'">
              {{ t.direction === 'buy' ? '买入' : '卖出' }}
            </span>
            <span>{{ t.name || t.code }}</span>
            <span>{{ t.price }} × {{ t.quantity }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 交易台账 -->
    <div v-show="tab === 'trades'">
      <div class="panel">
        <div class="panel-title">录入交易</div>
        <form class="trade-form" @submit.prevent="onAddTrade">
          <input v-model="form.code" placeholder="代码 000001" required maxlength="6" />
          <select v-model="form.direction">
            <option value="buy">买入</option>
            <option value="sell">卖出</option>
          </select>
          <input v-model.number="form.price" type="number" step="0.001" min="0.001" placeholder="价格" required />
          <input v-model.number="form.quantity" type="number" step="100" min="1" placeholder="数量(股)" required />
          <input v-model.number="form.fee" type="number" step="0.01" min="0" placeholder="费用(元)" />
          <input v-model="form.traded_at" type="datetime-local" required />
          <input v-model="form.note" placeholder="备注（可选）" class="note-field" />
          <button type="submit" class="btn-primary" :disabled="adding">{{ adding ? '提交中...' : '添加' }}</button>
        </form>
        <div v-if="formError" class="error-message">{{ formError }}</div>
      </div>

      <div class="panel">
        <div class="panel-title">
          交易记录（{{ trades.length }} 条）
          <input v-model="filterCode" class="filter-input" placeholder="按代码过滤" @input="loadTrades" />
        </div>
        <div v-if="!trades.length" class="empty">暂无交易记录</div>
        <table v-else class="result-table">
          <thead>
            <tr>
              <th>时间</th><th>代码</th><th>名称</th><th>方向</th>
              <th>价格</th><th>数量</th><th>金额</th><th>费用</th><th>备注</th><th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in trades" :key="t.id">
              <td class="time">{{ formatDateTime(t.traded_at) }}</td>
              <td class="code">{{ t.code }}</td>
              <td>{{ t.name }}</td>
              <td>
                <span class="status-tag" :class="t.direction === 'buy' ? 'tag-up' : 'tag-down'">
                  {{ t.direction === 'buy' ? '买入' : '卖出' }}
                </span>
              </td>
              <td>{{ t.price }}</td>
              <td>{{ t.quantity }}</td>
              <td>{{ fmtMoney(t.amount) }}</td>
              <td>{{ t.fee }}</td>
              <td class="note-cell">{{ t.note || '-' }}</td>
              <td><button class="btn-link danger" @click="onDeleteTrade(t.id)">删除</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 当前持仓 -->
    <div v-show="tab === 'positions'">
      <div class="panel">
        <div class="panel-title">当前持仓（FIFO 成本，按最新收盘价估值）</div>
        <div v-if="!positions.length" class="empty">暂无持仓</div>
        <table v-else class="result-table">
          <thead>
            <tr>
              <th>代码</th><th>名称</th><th>持仓数量</th><th>成本价</th><th>最新价</th>
              <th>浮动盈亏</th><th>浮盈%</th><th>已实现盈亏</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in positions" :key="p.code">
              <td class="code">{{ p.code }}</td>
              <td>{{ p.name }}</td>
              <td>{{ p.quantity }}</td>
              <td>{{ p.cost_price }}</td>
              <td>{{ p.close ?? '-' }}</td>
              <td :class="changeClass(p.unrealized_pnl)">{{ p.unrealized_pnl !== null ? fmtMoney(p.unrealized_pnl) : '-' }}</td>
              <td :class="changeClass(p.unrealized_pct)">{{ p.unrealized_pct !== null ? p.unrealized_pct + '%' : '-' }}</td>
              <td :class="changeClass(p.realized_pnl)">{{ fmtMoney(p.realized_pnl) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  createJournalTrade,
  deleteJournalTrade,
  deleteNote,
  fetchJournalStats,
  fetchJournalTrades,
  fetchNote,
  fetchNoteDates,
  fetchPositions,
  saveNote,
  type JournalStats,
  type JournalTrade,
  type PositionItem,
} from '../api/client'

const tab = ref<'note' | 'trades' | 'positions'>('note')
const stats = ref<JournalStats>({ total_realized: 0, win_count: 0, loss_count: 0, win_rate: null, sell_count: 0, buy_count: 0, total_fee: 0 })

// ===== 日历与笔记 =====
const today = new Date()
const calYear = ref(today.getFullYear())
const calMonth = ref(today.getMonth() + 1)
const noteDates = ref<Set<string>>(new Set())
const tradeDates = ref<Set<string>>(new Set())
const selectedDate = ref(formatDate(today))
const noteContent = ref('')
const noteCodes = ref('')
const noteExists = ref(false)
const saving = ref(false)
const savedTip = ref(false)
const dayTrades = ref<JournalTrade[]>([])

function formatDate(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const calendarCells = computed(() => {
  const y = calYear.value
  const m = calMonth.value
  const first = new Date(y, m - 1, 1)
  // 周一为一周起点
  const startOffset = (first.getDay() + 6) % 7
  const daysInMonth = new Date(y, m, 0).getDate()
  const daysInPrev = new Date(y, m - 1, 0).getDate()
  const cells: { key: string; date: string; day: number; inMonth: boolean; isToday: boolean; hasNote: boolean; hasTrade: boolean }[] = []
  const todayStr = formatDate(new Date())

  const pushCell = (d: Date, inMonth: boolean) => {
    const ds = formatDate(d)
    cells.push({
      key: ds,
      date: ds,
      day: d.getDate(),
      inMonth,
      isToday: ds === todayStr,
      hasNote: noteDates.value.has(ds),
      hasTrade: tradeDates.value.has(ds),
    })
  }
  for (let i = startOffset - 1; i >= 0; i--) pushCell(new Date(y, m - 2, daysInPrev - i), false)
  for (let d = 1; d <= daysInMonth; d++) pushCell(new Date(y, m - 1, d), true)
  let next = 1
  while (cells.length % 7 !== 0) pushCell(new Date(y, m, next++), false)
  return cells
})

async function loadMonthMarks() {
  const data = await fetchNoteDates(calYear.value, calMonth.value)
  noteDates.value = new Set(data.note_dates)
  tradeDates.value = new Set(data.trade_dates)
}

function shiftMonth(delta: number) {
  let m = calMonth.value + delta
  if (m < 1) { calYear.value--; m = 12 }
  if (m > 12) { calYear.value++; m = 1 }
  calMonth.value = m
  loadMonthMarks()
}

async function selectDate(d: string) {
  selectedDate.value = d
  savedTip.value = false
  const note = await fetchNote(d)
  noteContent.value = note.content
  noteCodes.value = note.codes.join(',')
  noteExists.value = !!note.content
  dayTrades.value = await fetchJournalTrades(undefined, d, d)
}

async function onSaveNote() {
  saving.value = true
  try {
    const codes = noteCodes.value.split(/[,，\s]+/).map((s) => s.trim()).filter(Boolean)
    await saveNote(selectedDate.value, noteContent.value, codes)
    noteExists.value = !!noteContent.value
    savedTip.value = true
    setTimeout(() => (savedTip.value = false), 2000)
    loadMonthMarks()
  } finally {
    saving.value = false
  }
}

async function onDeleteNote() {
  await deleteNote(selectedDate.value)
  noteContent.value = ''
  noteCodes.value = ''
  noteExists.value = false
  loadMonthMarks()
}

// ===== 交易台账 =====
const trades = ref<JournalTrade[]>([])
const filterCode = ref('')
const adding = ref(false)
const formError = ref('')
const form = reactive({
  code: '',
  direction: 'buy' as 'buy' | 'sell',
  price: null as number | null,
  quantity: null as number | null,
  fee: 0,
  traded_at: '',
  note: '',
})

async function loadTrades() {
  trades.value = await fetchJournalTrades(filterCode.value || undefined)
}

async function onAddTrade() {
  adding.value = true
  formError.value = ''
  try {
    await createJournalTrade({
      stock_code: form.code.trim(),
      direction: form.direction,
      price: form.price!,
      quantity: form.quantity!,
      fee: form.fee || 0,
      traded_at: new Date(form.traded_at).toISOString(),
      note: form.note || null,
    })
    form.code = ''
    form.price = null
    form.quantity = null
    form.fee = 0
    form.note = ''
    await Promise.all([loadTrades(), loadStats(), loadMonthMarks()])
  } catch (err: any) {
    formError.value = err?.response?.data?.detail || '添加失败'
  } finally {
    adding.value = false
  }
}

async function onDeleteTrade(id: number) {
  if (!confirm('确认删除这条交易记录？')) return
  await deleteJournalTrade(id)
  await Promise.all([loadTrades(), loadStats(), loadMonthMarks()])
}

// ===== 持仓 =====
const positions = ref<PositionItem[]>([])

async function loadPositions() {
  positions.value = await fetchPositions()
}

async function loadStats() {
  stats.value = await fetchJournalStats()
}

function switchTab(t: 'note' | 'trades' | 'positions') {
  tab.value = t
  if (t === 'trades') loadTrades()
  if (t === 'positions') loadPositions()
}

function changeClass(n: number | null | undefined) {
  if (n === null || n === undefined) return ''
  return n >= 0 ? 'up' : 'down'
}

function fmtMoney(v: number) {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatDateTime(iso: string) {
  return iso.slice(0, 16).replace('T', ' ')
}

onMounted(() => {
  // 默认交易时间填当前时间
  const now = new Date()
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset())
  form.traded_at = now.toISOString().slice(0, 16)
  loadStats()
  loadMonthMarks()
  selectDate(selectedDate.value)
})
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
  display: flex;
  align-items: center;
  gap: 12px;
}

/* 日历 */
.note-layout {
  display: grid;
  grid-template-columns: 340px 1fr;
  gap: 16px;
}

.cal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  color: #e5e7eb;
  font-weight: 600;
  margin-bottom: 12px;
}

.cal-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;
}

.cal-week {
  text-align: center;
  font-size: 11px;
  color: #6b7280;
  padding: 4px 0;
}

.cal-cell {
  aspect-ratio: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: #d1d5db;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
}

.cal-cell:hover { background: #374151; }
.cal-cell.other { color: #4b5563; }
.cal-cell.today { border: 1px solid #60a5fa; }
.cal-cell.selected { background: #2563eb; color: #fff; }

.dots {
  display: flex;
  gap: 3px;
  height: 6px;
  margin-top: 2px;
}

.dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  display: inline-block;
}

.note-dot { background: #60a5fa; }
.trade-dot { background: #f59e0b; }

.cal-legend {
  display: flex;
  gap: 16px;
  margin-top: 12px;
  font-size: 11px;
  color: #9ca3af;
}

.cal-legend .dot { margin-right: 4px; }

/* 笔记编辑 */
.note-editor {
  width: 100%;
  background: #111827;
  border: 1px solid #374151;
  border-radius: 8px;
  color: #e5e7eb;
  padding: 12px;
  font-size: 14px;
  line-height: 1.6;
  resize: vertical;
  box-sizing: border-box;
}

.codes-input {
  width: 100%;
  margin-top: 10px;
  background: #111827;
  border: 1px solid #374151;
  border-radius: 6px;
  color: #e5e7eb;
  padding: 8px 12px;
  font-size: 13px;
  box-sizing: border-box;
}

.editor-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}

.saved-tip {
  font-size: 12px;
  color: #22c55e;
}

.day-trades {
  margin-top: 18px;
  border-top: 1px solid #374151;
  padding-top: 14px;
}

.day-trade-item {
  display: flex;
  gap: 12px;
  align-items: center;
  font-size: 13px;
  color: #d1d5db;
  padding: 6px 0;
}

/* 台账表单 */
.trade-form {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.trade-form input,
.trade-form select {
  background: #111827;
  border: 1px solid #374151;
  border-radius: 6px;
  color: #e5e7eb;
  padding: 8px 10px;
  font-size: 13px;
  width: 130px;
}

.trade-form .note-field {
  flex: 1;
  min-width: 160px;
}

.filter-input {
  background: #111827;
  border: 1px solid #374151;
  border-radius: 6px;
  color: #e5e7eb;
  padding: 5px 10px;
  font-size: 12px;
  width: 110px;
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

.result-table .code,
.result-table .time {
  color: #9ca3af;
}

.note-cell {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #9ca3af;
}

.status-tag {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.tag-up { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
.tag-down { background: rgba(34, 197, 94, 0.15); color: #22c55e; }

.btn-primary {
  padding: 8px 18px;
  border-radius: 6px;
  border: none;
  background: #2563eb;
  color: #fff;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-primary:hover:not(:disabled) { background: #1d4ed8; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-link {
  background: none;
  border: none;
  color: #60a5fa;
  font-size: 13px;
  cursor: pointer;
  padding: 4px 8px;
}

.btn-link.danger { color: #ef4444; }

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
  margin-top: 12px;
}
</style>
