<template>
  <div class="page">
    <div class="page-header">
      <h1>系统监控</h1>
      <div class="actions">
        <span class="generated">更新于 {{ formatTime(status?.generated_at) }}</span>
        <button class="btn-secondary" @click="load" :disabled="loading">{{ loading ? '刷新中...' : '刷新' }}</button>
      </div>
    </div>

    <div v-if="error" class="error-message">{{ error }}</div>
    <div v-if="loading && !status" class="loading-text">加载中...</div>

    <template v-else-if="status">
      <!-- 总览 -->
      <div class="stats-row">
        <div class="stat-card">
          <div class="stat-label">数据库体积</div>
          <div class="stat-value">{{ status.database.size_mb ?? '-' }} MB</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">缓存表</div>
          <div class="stat-value">
            <span class="ok-text">{{ countByStatus(status.tables, 'ok') }}</span> 正常
            <template v-if="countByStatus(status.tables, 'stale')">
              / <span class="warn-text">{{ countByStatus(status.tables, 'stale') }}</span> 滞后
            </template>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-label">定时任务</div>
          <div class="stat-value">
            <span class="ok-text">{{ countByStatus(status.cron_jobs, 'ok') }}</span> 正常
            <template v-if="countByStatus(status.cron_jobs, 'error')">
              / <span class="err-text">{{ countByStatus(status.cron_jobs, 'error') }}</span> 异常
            </template>
            <template v-if="countByStatus(status.cron_jobs, 'stale')">
              / <span class="warn-text">{{ countByStatus(status.cron_jobs, 'stale') }}</span> 滞后
            </template>
          </div>
        </div>
      </div>

      <!-- 定时任务 -->
      <div class="panel">
        <div class="panel-title">定时任务</div>
        <table class="result-table">
          <thead>
            <tr><th>状态</th><th>任务</th><th>计划</th><th>最近运行</th><th>日志</th></tr>
          </thead>
          <tbody>
            <template v-for="job in status.cron_jobs" :key="job.log">
              <tr>
                <td><span class="badge" :class="badgeClass(job.status)">{{ statusText(job.status) }}</span></td>
                <td>{{ job.name }}</td>
                <td class="muted">{{ job.schedule }}</td>
                <td class="muted">{{ formatTime(job.last_run) }}</td>
                <td class="muted">{{ job.log }}</td>
              </tr>
              <tr v-if="job.error" class="error-row">
                <td></td>
                <td colspan="4">
                  <div class="error-line">{{ job.error }}</div>
                  <div v-for="(line, i) in job.last_lines" :key="i" class="log-line">{{ line }}</div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <!-- 缓存表 -->
      <div class="panel">
        <div class="panel-title">数据缓存</div>
        <table class="result-table">
          <thead>
            <tr><th>状态</th><th>数据</th><th>表</th><th>最新日期</th><th>行数</th></tr>
          </thead>
          <tbody>
            <tr v-for="t in status.tables" :key="t.table">
              <td><span class="badge" :class="badgeClass(t.status)">{{ statusText(t.status) }}</span></td>
              <td>{{ t.label }}</td>
              <td class="muted">{{ t.table }}</td>
              <td class="muted">{{ t.max_date ?? '-' }}</td>
              <td class="muted">{{ t.rows.toLocaleString() }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { fetchSystemStatus, type SystemStatus } from '../api/client'

const status = ref<SystemStatus | null>(null)
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    status.value = await fetchSystemStatus()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

function countByStatus(items: { status: string }[], s: string) {
  return items.filter((i) => i.status === s).length
}

function badgeClass(s: string) {
  return { ok: 'badge-ok', stale: 'badge-warn', error: 'badge-err', missing: 'badge-muted', empty: 'badge-muted' }[s] || ''
}

function statusText(s: string) {
  return { ok: '正常', stale: '滞后', error: '异常', missing: '缺失', empty: '空' }[s] || s
}

function formatTime(iso?: string | null) {
  return iso ? iso.slice(0, 16).replace('T', ' ') : '-'
}

onMounted(load)
</script>

<style scoped>
.page {
  padding: 20px;
  max-width: 1200px;
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
  align-items: center;
  gap: 12px;
}

.generated {
  font-size: 12px;
  color: #6b7280;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
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

.ok-text { color: #22c55e; }
.warn-text { color: #f59e0b; }
.err-text { color: #ef4444; }

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

.result-table .muted {
  color: #9ca3af;
}

.badge {
  padding: 2px 10px;
  border-radius: 4px;
  font-size: 12px;
}

.badge-ok { background: rgba(34, 197, 94, 0.15); color: #22c55e; }
.badge-warn { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
.badge-err { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
.badge-muted { background: #374151; color: #9ca3af; }

.error-row td {
  border-bottom: 1px solid #111827;
  padding-top: 0;
}

.error-line {
  color: #ef4444;
  font-size: 12px;
  margin-bottom: 6px;
}

.log-line {
  color: #6b7280;
  font-size: 11px;
  font-family: monospace;
  line-height: 1.5;
}

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

.loading-text {
  color: #9ca3af;
  padding: 40px;
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
</style>
