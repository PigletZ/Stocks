<template>
  <div class="stock-picker">
    <div class="picker-input-wrap">
      <div class="chips">
        <span v-for="s in modelValue" :key="s.code" class="chip">
          {{ s.name }}<em>{{ s.code }}</em>
          <button class="chip-remove" @click="remove(s.code)">×</button>
        </span>
        <input
          v-model="keyword"
          class="picker-input"
          :placeholder="modelValue.length ? '' : '搜索股票代码/名称，最多 10 只（不支持银行股）'"
          @input="onInput"
          @focus="onInput"
          @blur="onBlur"
        />
      </div>
      <div v-if="dropdownVisible" class="dropdown">
        <div v-if="searching" class="dropdown-hint">搜索中…</div>
        <div v-else-if="!candidates.length" class="dropdown-hint">无匹配结果</div>
        <div
          v-for="item in candidates"
          :key="item.code"
          class="dropdown-item"
          @mousedown.prevent="pick(item)"
        >
          <span class="di-name">{{ item.name }}</span>
          <span class="di-code">{{ item.code }}</span>
          <span class="di-industry">{{ item.industry || '' }}</span>
        </div>
      </div>
    </div>
    <span class="picker-count" :class="{ full: modelValue.length >= MAX }">
      {{ modelValue.length }}/{{ MAX }}
    </span>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { fetchStockList, type StockListItem } from '../../api/client'

const MAX = 10

interface PickedStock {
  code: string
  name: string
}

const props = defineProps<{ modelValue: PickedStock[] }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: PickedStock[]): void }>()

const keyword = ref('')
const candidates = ref<StockListItem[]>([])
const searching = ref(false)
const dropdownVisible = ref(false)
let searchTimer: ReturnType<typeof setTimeout> | null = null

function onInput() {
  dropdownVisible.value = true
  if (searchTimer) clearTimeout(searchTimer)
  const kw = keyword.value.trim()
  if (!kw) {
    candidates.value = []
    return
  }
  searchTimer = setTimeout(async () => {
    searching.value = true
    try {
      const res = await fetchStockList(kw, undefined, 1, 12)
      // 过滤银行股与已选股票
      const picked = new Set(props.modelValue.map((s) => s.code))
      candidates.value = res.items.filter(
        (it) => !picked.has(it.code) && !(it.industry && it.industry.includes('银行'))
      )
    } catch {
      candidates.value = []
    } finally {
      searching.value = false
    }
  }, 250)
}

function onBlur() {
  // 延迟关闭，让 mousedown 先触发
  setTimeout(() => (dropdownVisible.value = false), 150)
}

function pick(item: StockListItem) {
  if (props.modelValue.length >= MAX) return
  emit('update:modelValue', [...props.modelValue, { code: item.code, name: item.name }])
  keyword.value = ''
  candidates.value = []
}

function remove(code: string) {
  emit(
    'update:modelValue',
    props.modelValue.filter((s) => s.code !== code)
  )
}
</script>

<style scoped>
.stock-picker {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.picker-input-wrap {
  position: relative;
  flex: 1;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  background: #1f2937;
  border: 1px solid #374151;
  border-radius: 6px;
  padding: 8px 10px;
  min-height: 44px;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: #2563eb;
  color: #fff;
  font-size: 13px;
  padding: 4px 8px;
  border-radius: 4px;
}

.chip em {
  font-style: normal;
  font-size: 11px;
  opacity: 0.75;
}

.chip-remove {
  background: none;
  border: none;
  color: #fff;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  opacity: 0.7;
  padding: 0;
}

.chip-remove:hover {
  opacity: 1;
}

.picker-input {
  flex: 1;
  min-width: 220px;
  background: transparent;
  border: none;
  outline: none;
  color: #e5e7eb;
  font-size: 14px;
  padding: 4px 2px;
}

.picker-input::placeholder {
  color: #6b7280;
}

.dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  background: #111827;
  border: 1px solid #374151;
  border-radius: 6px;
  max-height: 320px;
  overflow-y: auto;
  z-index: 30;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
}

.dropdown-hint {
  padding: 12px;
  color: #6b7280;
  font-size: 13px;
  text-align: center;
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  cursor: pointer;
  font-size: 13px;
}

.dropdown-item:hover {
  background: #1a2230;
}

.di-name {
  color: #ffffff;
  font-weight: 600;
}

.di-code {
  color: #60a5fa;
}

.di-industry {
  margin-left: auto;
  color: #9ca3af;
  font-size: 12px;
}

.picker-count {
  color: #9ca3af;
  font-size: 13px;
  padding-top: 12px;
  white-space: nowrap;
}

.picker-count.full {
  color: #f59e0b;
}
</style>
