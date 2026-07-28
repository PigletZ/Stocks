<template>
  <div class="page">
    <div class="page-header">
      <h1>通用选股器</h1>
    </div>

    <!-- 条件构建器 -->
    <div class="panel">
      <div class="panel-title">筛选条件（AND 组合）</div>
      <div v-for="(c, i) in conditions" :key="i" class="cond-row">
        <select v-model="c.field" class="field-select">
          <option v-for="f in FIELD_OPTIONS" :key="f.value" :value="f.value">{{ f.label }}</option>
        </select>
        <select v-model="c.op" class="op-select">
          <option v-for="op in OPS" :key="op" :value="op">{{ op }}</option>
        </select>
        <input v-model.number="c.value" type="number" step="any" class="value-input" />
        <span class="unit">{{ fieldUnit(c.field) }}</span>
        <button class="btn-link danger" @click="conditions.splice(i, 1)">删除</button>
      </div>
      <div class="cond-actions">
        <button class="btn-secondary" @click="addCondition">+ 添加条件</button>
        <label class="filter-check">
          <input type="checkbox" v-model="applyFilters" />
          排除 ST/科创/创业/北交/次新
        </label>
        <input type="date" v-model="tradeDate" class="date-input" />
        <button class="btn-primary" @click="run" :disabled="loading || !conditions.length">
          {{ loading ? '筛选中...' : '执行筛选' }}
        </button>
      </div>
      <div v-if="error" class="error-message">{{ error }}</div>
    </div>

    <!-- 预设 -->
    <div class="panel preset-panel">
      <div class="preset-group">
        <select v-model="selectedPreset" class="preset-select" @change="loadPreset">
          <option :value="0">选择预设...</option>
          <option v-for="p in presets" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
        <button v-if="selectedPreset" class="btn-link danger" @click="onDeletePreset">删除预设</button>
      </div>
      <div class="preset-group">
        <input v-model="presetName" class="preset-name" placeholder="预设名称" />
        <button class="btn-secondary" @click="onSavePreset" :disabled="!presetName.trim() || !conditions.length">
          保存为预设
        </button>
        <span class="hint">保存后可在「策略选股」页作为自定义策略使用</span>
      </div>
    </div>

    <!-- 结果 -->
    <div v-if="result" class="panel">
      <div class="panel-title">{{ result.trade_date }} 命中 {{ result.total }} 只（点击行查看 K 线）</div>
      <div v-if="!result.items.length" class="empty">无符合条件的股票</div>
      <table v-else class="result-table">
        <thead>
          <tr>
            <th>代码</th><th>名称</th><th>最新价</th><th>涨跌幅</th><th>换手率</th>
            <th>成交额</th><th>流通市值</th><th>连板</th><th>量比</th><th>均线多头</th><th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in result.items" :key="item.code" @click="openDetail(item.code, item.name)">
            <td class="code">{{ item.code }}</td>
            <td>{{ item.name }}</td>
            <td>{{ item.close ?? '-' }}</td>
            <td :class="changeClass(item.change_pct)">{{ item.change_pct !== null ? item.change_pct.toFixed(2) + '%' : '-' }}</td>
            <td>{{ item.turnover_rate !== null ? item.turnover_rate.toFixed(2) + '%' : '-' }}</td>
            <td>{{ item.amount !== null ? item.amount + '亿' : '-' }}</td>
            <td>{{ item.float_mv !== null ? item.float_mv + '亿' : '-' }}</td>
            <td><span v-if="item.limit_times > 0" class="tag-board">{{ item.limit_times }}板</span><span v-else>-</span></td>
            <td>{{ item.volume_ratio ?? '-' }}</td>
            <td><span v-if="item.ma_bull" class="tag-bull">多头</span><span v-else>-</span></td>
            <td><button class="btn-link" @click.stop="onAddWatchlist(item.code)">加自选</button></td>
          </tr>
        </tbody>
      </table>
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
import { onMounted, reactive, ref } from 'vue'
import {
  addToWatchlist,
  createScreenPreset,
  deleteScreenPreset,
  fetchScreenPresets,
  runScreener,
  type ScreenCondition,
  type ScreenPreset,
  type ScreenerResult,
} from '../api/client'
import PigletStockDetailPopup from '../components/strategy/PigletStockDetailPopup.vue'

const FIELD_OPTIONS = [
  { value: 'change_pct', label: '涨跌幅', unit: '%' },
  { value: 'turnover_rate', label: '换手率', unit: '%' },
  { value: 'amount', label: '成交额', unit: '亿' },
  { value: 'float_mv', label: '流通市值', unit: '亿' },
  { value: 'total_mv', label: '总市值', unit: '亿' },
  { value: 'pe_ttm', label: 'PE(TTM)', unit: '' },
  { value: 'pb', label: 'PB', unit: '' },
  { value: 'limit_times', label: '连板数', unit: '板' },
  { value: 'volume_ratio', label: '量比', unit: '' },
  { value: 'high_n_days', label: 'N日新高', unit: '天' },
  { value: 'ma_bull', label: '均线多头(是=1)', unit: '' },
]
const OPS = ['>=', '<=', '>', '<', '=']

const conditions = reactive<ScreenCondition[]>([
  { field: 'change_pct', op: '>=', value: 3 },
  { field: 'turnover_rate', op: '>=', value: 5 },
])
const applyFilters = ref(true)
const tradeDate = ref('')
const loading = ref(false)
const error = ref('')
const result = ref<ScreenerResult | null>(null)

const presets = ref<ScreenPreset[]>([])
const selectedPreset = ref(0)
const presetName = ref('')

const detail = reactive({ visible: false, code: '', name: '' })

function fieldUnit(f: string) {
  return FIELD_OPTIONS.find((o) => o.value === f)?.unit ?? ''
}

function addCondition() {
  conditions.push({ field: 'amount', op: '>=', value: 2 })
}

function changeClass(n: number | null) {
  if (n === null) return ''
  return n >= 0 ? 'up' : 'down'
}

function openDetail(code: string, name: string) {
  detail.code = code
  detail.name = name
  detail.visible = true
}

async function run() {
  loading.value = true
  error.value = ''
  try {
    result.value = await runScreener([...conditions], tradeDate.value || undefined, applyFilters.value)
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '筛选失败'
  } finally {
    loading.value = false
  }
}

async function loadPresets() {
  presets.value = await fetchScreenPresets()
}

function loadPreset() {
  const p = presets.value.find((x) => x.id === selectedPreset.value)
  if (!p) return
  conditions.splice(0, conditions.length, ...p.conditions.map((c) => ({ ...c })))
  run()
}

async function onSavePreset() {
  error.value = ''
  try {
    await createScreenPreset(presetName.value.trim(), [...conditions])
    presetName.value = ''
    await loadPresets()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '保存失败'
  }
}

async function onDeletePreset() {
  await deleteScreenPreset(selectedPreset.value)
  selectedPreset.value = 0
  await loadPresets()
}

async function onAddWatchlist(code: string) {
  try {
    await addToWatchlist(code)
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '添加自选失败'
  }
}

onMounted(loadPresets)
</script>

<style scoped>
.page {
  padding: 20px;
  max-width: 1400px;
}

.page-header h1 {
  font-size: 20px;
  color: #e5e7eb;
  margin-bottom: 16px;
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

.cond-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.field-select { width: 160px; }
.op-select { width: 70px; }
.value-input { width: 110px; }

.cond-row select,
.cond-row input {
  background: #111827;
  border: 1px solid #374151;
  border-radius: 6px;
  color: #e5e7eb;
  padding: 8px 10px;
  font-size: 13px;
}

.unit {
  color: #6b7280;
  font-size: 12px;
  width: 24px;
}

.cond-actions {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 14px;
}

.filter-check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #9ca3af;
  cursor: pointer;
}

.date-input {
  background: #111827;
  border: 1px solid #374151;
  border-radius: 6px;
  color: #e5e7eb;
  padding: 7px 10px;
  font-size: 13px;
}

.preset-panel {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.preset-group {
  display: flex;
  align-items: center;
  gap: 10px;
}

.preset-select,
.preset-name {
  background: #111827;
  border: 1px solid #374151;
  border-radius: 6px;
  color: #e5e7eb;
  padding: 7px 10px;
  font-size: 13px;
  width: 180px;
}

.hint {
  font-size: 12px;
  color: #6b7280;
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

.result-table tbody tr {
  cursor: pointer;
}

.result-table tbody tr:hover {
  background: #111827;
}

.result-table .code {
  color: #9ca3af;
}

.up { color: #ef4444; }
.down { color: #22c55e; }

.tag-board {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 12px;
}

.tag-bull {
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 12px;
}

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

.btn-secondary {
  padding: 8px 14px;
  border-radius: 6px;
  border: 1px solid #374151;
  background: #1f2937;
  color: #d1d5db;
  font-size: 13px;
  cursor: pointer;
}

.btn-secondary:hover:not(:disabled) {
  border-color: #60a5fa;
  color: #60a5fa;
}

.btn-secondary:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-link {
  background: none;
  border: none;
  color: #60a5fa;
  font-size: 13px;
  cursor: pointer;
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
