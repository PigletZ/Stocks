<template>
  <div class="watchlist">
    <div class="header">
      <h1>自选股票</h1>
      <div class="header-actions">
        <button class="btn-secondary" @click="addStockModal = true">添加自选</button>
        <button class="btn-secondary" @click="openGroupModal('create')">新建分组</button>
      </div>
    </div>

    <div v-for="group in groups" :key="group.id" class="group">
      <div class="group-title">
        <span class="group-name" @click="toggleGroup(group.id)">
          <span class="arrow" :class="{ expanded: !collapsed[group.id] }">▶</span>
          {{ group.name }}（{{ group.stocks.length }}）
        </span>
        <div class="group-actions">
          <button class="btn-link" @click="openGroupModal('rename', group)">重命名</button>
          <button class="btn-link danger" @click="confirmDeleteGroup(group)">删除</button>
        </div>
      </div>
      <div v-show="!collapsed[group.id]" class="group-items">
        <div v-for="item in group.stocks" :key="item.code" class="stock-card">
          <div class="stock-info">
            <div class="stock-name">{{ item.name }} <span class="stock-code">{{ item.code }}</span></div>
            <div class="stock-meta">
              {{ item.exchange }} · {{ item.industry || '无行业' }}
            </div>
            <div v-if="item.close != null" class="stock-quote">
              <span :class="{ up: (item.change_pct || 0) > 0, down: (item.change_pct || 0) < 0 }">
                {{ item.close.toFixed(2) }} {{ formatChange(item.change_pct) }}
              </span>
              <span v-if="item.turnover_rate != null" class="turnover">换手 {{ item.turnover_rate.toFixed(2) }}%</span>
            </div>
            <div v-if="item.position" class="stock-position">
              <span class="pos-qty">持仓 {{ item.position.quantity }}股 @ {{ item.position.cost_price }}</span>
              <span v-if="item.position.unrealized_pct != null" :class="item.position.unrealized_pct >= 0 ? 'up' : 'down'">
                {{ item.position.unrealized_pct >= 0 ? '+' : '' }}{{ item.position.unrealized_pct }}%
                （{{ fmtMoney(item.position.unrealized_pnl) }}）
              </span>
              <span class="pos-source">{{ item.position.source === 'journal' ? '台账' : '手动' }}</span>
            </div>
          </div>
          <div class="stock-actions">
            <router-link :to="`/stock/${item.code}`" class="btn-link">复盘</router-link>
            <button class="btn-link" @click="openHoldingModal(item)">持仓</button>
            <button class="btn-link" @click="openMoveModal(item)">移动</button>
            <button class="btn-link danger" @click="confirmRemove(item)">删除</button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="groups.length === 0" class="empty">
      暂无自选股，请从<router-link to="/stocks">全市场股票</router-link>中添加
    </div>

    <!-- 新建/重命名分组 -->
    <BaseModal :visible="groupModal.visible" :title="groupModal.mode === 'create' ? '新建分组' : '重命名分组'" @close="groupModal.visible = false">
      <input v-model="groupModal.name" class="modal-input" placeholder="分组名称" @keyup.enter="submitGroupModal" />
      <div v-if="groupModal.error" class="modal-error">{{ groupModal.error }}</div>
      <template #footer>
        <button class="btn-secondary" @click="groupModal.visible = false">取消</button>
        <button class="btn-primary" @click="submitGroupModal">确定</button>
      </template>
    </BaseModal>

    <!-- 删除确认 -->
    <BaseModal :visible="confirmModal.visible" :title="confirmModal.title" @close="confirmModal.visible = false">
      <p class="confirm-text">{{ confirmModal.text }}</p>
      <template #footer>
        <button class="btn-secondary" @click="confirmModal.visible = false">取消</button>
        <button class="btn-danger" @click="confirmModal.onConfirm">确认删除</button>
      </template>
    </BaseModal>

    <!-- 移动分组 -->
    <BaseModal :visible="moveModal.visible" title="移动到分组" @close="moveModal.visible = false">
      <div class="move-options">
        <button
          v-for="g in groups"
          :key="g.id"
          class="move-option"
          :class="{ current: g.id === moveModal.currentGroupId }"
          @click="submitMove(g.id)"
        >
          {{ g.name }}
        </button>
      </div>
    </BaseModal>

    <!-- 编辑持仓 -->
    <BaseModal :visible="holdingModal.visible" :title="`${holdingModal.name} 持仓`" @close="holdingModal.visible = false">
      <template v-if="holdingModal.source === 'journal'">
        <p class="confirm-text">
          当前持仓 {{ holdingModal.quantity }} 股，成本 {{ holdingModal.costPrice }}（由交易台账 FIFO 自动计算）。
        </p>
        <p class="hint-text">如需调整，请前往「复盘日志 → 交易台账」修改买卖记录。</p>
      </template>
      <template v-else>
        <div class="form-row">
          <label>成本价</label>
          <input v-model.number="holdingModal.costPrice" type="number" step="0.001" min="0.001" class="modal-input" />
        </div>
        <div class="form-row">
          <label>数量（股）</label>
          <input v-model.number="holdingModal.quantity" type="number" step="100" min="1" class="modal-input" />
        </div>
        <div v-if="holdingModal.error" class="modal-error">{{ holdingModal.error }}</div>
      </template>
      <template #footer>
        <template v-if="holdingModal.source === 'manual'">
          <button class="btn-danger" @click="submitDeleteHolding">清除持仓</button>
          <button class="btn-primary" @click="submitHolding">保存</button>
        </template>
        <button v-else class="btn-secondary" @click="holdingModal.visible = false">关闭</button>
      </template>
    </BaseModal>

    <!-- 添加自选 -->
    <BaseModal :visible="addStockModal" title="添加自选" @close="addStockModal = false">
      <input v-model="stockSearch" class="modal-input" placeholder="输入代码或名称搜索" @input="onSearchStock" />
      <div class="search-results">
        <div
          v-for="s in searchResults"
          :key="s.code"
          class="search-item"
          @click="addStock(s.code)"
        >
          <span>{{ s.name }}</span>
          <span class="code">{{ s.code }}</span>
        </div>
        <div v-if="stockSearch && !searchResults.length" class="hint-text">无匹配结果</div>
      </div>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue'
import {
  addToWatchlist,
  createWatchlistGroup,
  deleteHolding,
  deleteWatchlistGroup,
  fetchStockList,
  fetchWatchlistGroups,
  moveWatchlistGroup,
  removeFromWatchlist,
  renameWatchlistGroup,
  upsertHolding,
  type StockListItem,
  type WatchlistGroup,
  type WatchlistItem,
} from '../api/client'
import BaseModal from '../components/common/BaseModal.vue'

const groups = ref<WatchlistGroup[]>([])
const collapsed = reactive<Record<number, boolean>>({})

async function load() {
  try {
    groups.value = await fetchWatchlistGroups()
  } catch (err) {
    console.error('Failed to load watchlist', err)
  }
}

function toggleGroup(id: number) {
  collapsed[id] = !collapsed[id]
}

// ===== 分组新建/重命名 =====
const groupModal = reactive({ visible: false, mode: 'create' as 'create' | 'rename', id: 0, name: '', error: '' })

function openGroupModal(mode: 'create' | 'rename', group?: WatchlistGroup) {
  groupModal.mode = mode
  groupModal.id = group?.id ?? 0
  groupModal.name = group?.name ?? ''
  groupModal.error = ''
  groupModal.visible = true
}

async function submitGroupModal() {
  const name = groupModal.name.trim()
  if (!name) return
  try {
    if (groupModal.mode === 'create') {
      await createWatchlistGroup(name)
    } else {
      await renameWatchlistGroup(groupModal.id, name)
    }
    groupModal.visible = false
    await load()
  } catch (err: any) {
    groupModal.error = err?.response?.data?.detail || '操作失败'
  }
}

// ===== 删除确认（分组/股票通用） =====
const confirmModal = reactive({ visible: false, title: '', text: '', onConfirm: () => {} })

function confirmDeleteGroup(group: WatchlistGroup) {
  confirmModal.title = '删除分组'
  confirmModal.text = `确定删除分组「${group.name}」？组内股票将移至默认分组。`
  confirmModal.onConfirm = async () => {
    confirmModal.visible = false
    await deleteWatchlistGroup(group.id)
    await load()
  }
  confirmModal.visible = true
}

function confirmRemove(item: WatchlistItem) {
  confirmModal.title = '删除自选股'
  confirmModal.text = `确定从自选删除「${item.name} ${item.code}」？`
  confirmModal.onConfirm = async () => {
    confirmModal.visible = false
    await removeFromWatchlist(item.code)
    await load()
  }
  confirmModal.visible = true
}

// ===== 移动分组 =====
const moveModal = reactive({ visible: false, code: '', currentGroupId: 0 })

function openMoveModal(item: WatchlistItem) {
  moveModal.code = item.code
  moveModal.currentGroupId = item.group_id
  moveModal.visible = true
}

async function submitMove(groupId: number) {
  if (groupId === moveModal.currentGroupId) {
    moveModal.visible = false
    return
  }
  await moveWatchlistGroup(moveModal.code, groupId)
  moveModal.visible = false
  await load()
}

// ===== 持仓编辑 =====
const holdingModal = reactive({
  visible: false,
  code: '',
  name: '',
  source: 'none' as 'journal' | 'manual' | 'none',
  costPrice: null as number | null,
  quantity: null as number | null,
  error: '',
})

function openHoldingModal(item: WatchlistItem) {
  holdingModal.code = item.code
  holdingModal.name = item.name
  holdingModal.source = item.position?.source ?? 'none'
  holdingModal.costPrice = item.position?.cost_price ?? null
  holdingModal.quantity = item.position?.quantity ?? null
  holdingModal.error = ''
  holdingModal.visible = true
}

async function submitHolding() {
  if (!holdingModal.costPrice || !holdingModal.quantity) {
    holdingModal.error = '请填写成本价和数量'
    return
  }
  try {
    await upsertHolding(holdingModal.code, holdingModal.costPrice, holdingModal.quantity)
    holdingModal.visible = false
    await load()
  } catch (err: any) {
    holdingModal.error = err?.response?.data?.detail || '保存失败'
  }
}

async function submitDeleteHolding() {
  await deleteHolding(holdingModal.code)
  holdingModal.visible = false
  await load()
}

// ===== 添加自选 =====
const addStockModal = ref(false)
const stockSearch = ref('')
const searchResults = ref<StockListItem[]>([])
let searchTimer: ReturnType<typeof setTimeout> | null = null

function onSearchStock() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(async () => {
    if (!stockSearch.value.trim()) {
      searchResults.value = []
      return
    }
    const res = await fetchStockList(stockSearch.value.trim(), undefined, 1, 10)
    searchResults.value = res.items
  }, 300)
}

async function addStock(code: string) {
  try {
    await addToWatchlist(code)
    addStockModal.value = false
    stockSearch.value = ''
    searchResults.value = []
    await load()
  } catch (err: any) {
    alert(err?.response?.data?.detail || '添加失败')
  }
}

function formatChange(value?: number): string {
  if (value == null) return ''
  const sign = value > 0 ? '+' : ''
  return `（${sign}${value.toFixed(2)}%）`
}

function fmtMoney(v: number | null) {
  if (v === null) return '-'
  return (v >= 0 ? '+' : '') + v.toLocaleString('zh-CN', { maximumFractionDigits: 0 })
}

onMounted(() => {
  load()
})
</script>

<style scoped>
.watchlist {
  padding: 24px;
  height: 100%;
  overflow-y: auto;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.header h1 {
  font-size: 20px;
  font-weight: 600;
}

.header-actions {
  display: flex;
  gap: 10px;
}

.group {
  margin-bottom: 24px;
}

.group-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
  font-weight: 600;
  color: #9ca3af;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #1f2937;
}

.group-name {
  cursor: pointer;
  user-select: none;
  display: flex;
  align-items: center;
  gap: 8px;
}

.arrow {
  font-size: 10px;
  transition: transform 0.2s;
}

.arrow.expanded {
  transform: rotate(90deg);
}

.group-actions {
  display: flex;
  gap: 10px;
}

.group-items {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

.stock-card {
  background: #1f2937;
  border-radius: 8px;
  padding: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.stock-name {
  font-size: 15px;
  font-weight: 500;
  color: #fff;
  margin-bottom: 4px;
}

.stock-code {
  font-size: 12px;
  color: #9ca3af;
  font-weight: normal;
}

.stock-meta {
  font-size: 12px;
  color: #9ca3af;
  margin-bottom: 6px;
}

.stock-quote {
  display: flex;
  gap: 12px;
  font-size: 13px;
}

.stock-quote .up,
.up {
  color: #ef4444;
}

.stock-quote .down,
.down {
  color: #22c55e;
}

.turnover {
  color: #9ca3af;
}

.stock-position {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed #374151;
}

.pos-qty {
  color: #9ca3af;
}

.pos-source {
  background: #374151;
  color: #9ca3af;
  border-radius: 4px;
  padding: 1px 6px;
  font-size: 11px;
}

.stock-actions {
  display: flex;
  gap: 10px;
}

.btn-link {
  background: transparent;
  border: none;
  color: #60a5fa;
  cursor: pointer;
  font-size: 13px;
  text-decoration: none;
  padding: 0;
}

.btn-link:hover {
  color: #93c5fd;
}

.btn-link.danger {
  color: #f87171;
}

.btn-link.danger:hover {
  color: #fca5a5;
}

.btn-secondary {
  padding: 8px 14px;
  border-radius: 6px;
  border: 1px solid #374151;
  background: #1f2937;
  color: #fff;
  cursor: pointer;
  font-size: 13px;
}

.btn-secondary:hover {
  background: #374151;
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

.btn-primary:hover {
  background: #1d4ed8;
}

.btn-danger {
  padding: 8px 18px;
  border-radius: 6px;
  border: none;
  background: #dc2626;
  color: #fff;
  font-size: 13px;
  cursor: pointer;
}

.btn-danger:hover {
  background: #b91c1c;
}

.empty {
  color: #9ca3af;
  text-align: center;
  padding: 60px 0;
}

.empty a {
  color: #60a5fa;
  text-decoration: none;
}

/* 弹窗内容 */
.modal-input {
  width: 100%;
  background: #111827;
  border: 1px solid #374151;
  border-radius: 6px;
  color: #e5e7eb;
  padding: 9px 12px;
  font-size: 14px;
  box-sizing: border-box;
}

.modal-error {
  color: #ef4444;
  font-size: 12px;
  margin-top: 8px;
}

.confirm-text {
  color: #d1d5db;
  font-size: 14px;
  line-height: 1.6;
}

.hint-text {
  color: #6b7280;
  font-size: 12px;
  margin-top: 8px;
}

.form-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.form-row label {
  width: 80px;
  font-size: 13px;
  color: #9ca3af;
  flex-shrink: 0;
}

.move-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.move-option {
  padding: 10px 14px;
  border-radius: 6px;
  border: 1px solid #374151;
  background: #111827;
  color: #d1d5db;
  font-size: 14px;
  cursor: pointer;
  text-align: left;
}

.move-option:hover {
  border-color: #60a5fa;
}

.move-option.current {
  border-color: #2563eb;
  color: #60a5fa;
}

.search-results {
  margin-top: 10px;
  max-height: 300px;
  overflow-y: auto;
}

.search-item {
  display: flex;
  justify-content: space-between;
  padding: 9px 12px;
  border-radius: 6px;
  color: #e5e7eb;
  font-size: 14px;
  cursor: pointer;
}

.search-item:hover {
  background: #374151;
}

.search-item .code {
  color: #9ca3af;
}
</style>
