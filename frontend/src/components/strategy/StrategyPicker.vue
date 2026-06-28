<template>
  <div class="strategy-picker">
    <div class="field">
      <label>选择策略</label>
      <select
        :value="selectedStrategy"
        @change="$emit('update:selectedStrategy', ($event.target as HTMLSelectElement).value)"
      >
        <option v-for="s in strategies" :key="s.id" :value="s.id">
          {{ s.name }}
        </option>
      </select>
      <p v-if="currentStrategy" class="desc">{{ currentStrategy.description }}</p>
    </div>

    <div class="field">
      <label>选股日期</label>
      <input
        type="date"
        :value="tradeDate"
        @change="$emit('update:tradeDate', ($event.target as HTMLInputElement).value)"
      />
      <p class="desc">&nbsp;</p>
    </div>

    <div class="field field-button">
      <label>&nbsp;</label>
      <button
        class="btn-primary run-btn"
        :disabled="loading || !selectedStrategy"
        @click="$emit('run')"
      >
        {{ loading ? '选股中...' : '执行选股' }}
      </button>
      <p class="desc">&nbsp;</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { StrategyInfo } from '../../api/client'

const props = defineProps<{
  strategies: StrategyInfo[]
  selectedStrategy: string
  tradeDate: string
  loading: boolean
}>()

const currentStrategy = computed(() =>
  props.strategies.find((s) => s.id === props.selectedStrategy),
)

defineEmits<{
  (e: 'update:selectedStrategy', value: string): void
  (e: 'update:tradeDate', value: string): void
  (e: 'run'): void
}>()
</script>

<style scoped>
.strategy-picker {
  display: flex;
  align-items: flex-end;
  gap: 20px;
  flex-wrap: wrap;
  background: #111827;
  border: 1px solid #1f2937;
  border-radius: 8px;
  padding: 20px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 220px;
  flex: 1;
}

.field label {
  font-size: 13px;
  color: #9ca3af;
}

.field select,
.field input {
  padding: 8px 12px;
  background: #0b0f19;
  border: 1px solid #374151;
  border-radius: 6px;
  color: #e5e7eb;
  font-size: 14px;
}

.field .desc {
  font-size: 12px;
  color: #6b7280;
  margin: 0;
}

.field-button {
  flex: 0 0 auto;
  min-width: auto;
}

.run-btn {
  height: 38px;
  padding: 0 24px;
  white-space: nowrap;
}

.btn-primary {
  background: #2563eb;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-primary:hover:not(:disabled) {
  background: #1d4ed8;
}

.btn-primary:disabled {
  background: #1e3a8a;
  color: #93c5fd;
  cursor: not-allowed;
}
</style>
