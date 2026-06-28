<template>
  <div class="index-chart-popup">
    <div class="popup-header">
      <span class="popup-title">{{ name }} · 近30日</span>
      <span v-if="loading" class="loading-text">加载中...</span>
      <span v-else-if="error" class="error-text">{{ error }}</span>
    </div>
    <div class="popup-body">
      <ChartPanel
        v-if="bars.length > 0"
        :bars="bars"
        :current-index="bars.length - 1"
      />
      <div v-else-if="!loading" class="empty">暂无 K 线数据</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import ChartPanel from './ChartPanel.vue'
import { fetchIndexBars } from '../api/client'
import type { Bar } from '../api/client'

const props = defineProps<{
  code: string
  name: string
}>()

const bars = ref<Bar[]>([])
const loading = ref(false)
const error = ref('')

function formatDate(d: Date): string {
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

async function loadBars() {
  loading.value = true
  error.value = ''
  try {
    const end = formatDate(new Date())
    const start = formatDate(new Date(Date.now() - 90 * 24 * 60 * 60 * 1000))
    bars.value = await fetchIndexBars(props.code, start, end)
  } catch (err: any) {
    error.value = '加载失败'
    console.error('Failed to load index bars', err)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadBars()
})
</script>

<style scoped>
.index-chart-popup {
  width: 420px;
  background: #1f2937;
  border: 1px solid #374151;
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  overflow: hidden;
  z-index: 100;
}

.popup-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  border-bottom: 1px solid #374151;
  background: #111827;
}

.popup-title {
  font-size: 14px;
  font-weight: 600;
  color: #e5e7eb;
}

.loading-text,
.error-text {
  font-size: 12px;
}

.loading-text {
  color: #6b7280;
}

.error-text {
  color: #ef4444;
}

.popup-body {
  height: 260px;
  padding: 8px;
  display: flex;
  flex-direction: column;
}

.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #6b7280;
  font-size: 13px;
}
</style>
