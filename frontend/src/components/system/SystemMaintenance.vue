<template>
  <section class="maintenance-panel">
    <header><div><h2>补漏与备份</h2><p>任务在后台执行，关闭页面仍会继续。重复提交会复用正在执行或刚提交的任务。</p></div><button @click="refresh" :disabled="loading">刷新执行状态</button></header>
    <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <div class="cards"><article v-for="job in jobs" :key="job.action">
      <div class="row"><h3>{{ job.name }}</h3><strong :class="job.status">{{ labels[job.status] || job.status }}</strong></div>
      <p>{{ job.description }}</p><p class="message">{{ job.message }}</p>
      <template v-if="job.record"><p class="counts">成功 {{ job.record.succeeded }} · 失败 {{ job.record.failed }} · 待发布/核验 {{ job.record.deferred || 0 }} · 跳过 {{ job.record.skipped }}</p><small>写入 / 覆盖 {{ job.record.written_rows.toLocaleString() }} 条 · 更新 {{ time(job.record.updated_at || job.record.finished_at || job.record.started_at) }}</small>
        <details v-if="job.record.errors?.length || job.record.deferred_items?.length || job.record.history?.length"><summary>执行明细与此前结果</summary><p v-for="(line,i) in job.record.errors || []" :key="'error'+i" class="error">{{ line }}</p><p v-for="(line,i) in job.record.deferred_items || []" :key="'pending'+i">{{ line }}</p><p v-for="run in job.record.history || []" :key="run.started_at"><small>{{ time(run.started_at) }} · {{ labels[run.status] || run.status }} · 失败 {{ run.failed }} / 待核验 {{ run.deferred || 0 }}</small></p></details>
      </template>
      <button class="start" :disabled="!!submitting || !job.can_start" @click="start(job)">{{ submitting===job.action ? '正在提交…' : job.status==='queued' || job.status==='running' ? '正在后台执行' : job.next_allowed_at ? '稍后可再次执行' : job.name }}</button>
      <small v-if="job.requested_at">上次手动提交 {{ time(job.requested_at) }}</small>
    </article></div>
  </section>
</template>
<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { fetchMaintenanceJobs, startMaintenance, type MaintenanceJob } from '../../api/client'
import { createLatestLoader } from '../../utils/latestLoader'
const emit=defineEmits<{completed:[]}>()
const jobs=ref<MaintenanceJob[]>([]),loading=ref(false),submitting=ref(''),error=ref(''),notice=ref('')
const labels:Record<string,string>={idle:'按需执行',queued:'已提交',running:'运行中',success:'已完成',skipped:'已确认跳过',partial:'部分完成',unknown:'待核验',error:'失败',interrupted:'已中断'}
let disposed=false,timer:ReturnType<typeof setTimeout>|undefined
const waiting=new Set<string>()
const active=(job:MaintenanceJob)=>['queued','running'].includes(job.status)
const loader=createLatestLoader<MaintenanceJob[]>({pending:value=>loading.value=value,reject:()=>error.value='执行状态暂未读取成功。已提交的任务可能仍在运行，请刷新核对。',resolve:value=>{
  const completed=value.some(job=>waiting.has(job.action)&&!active(job))
  jobs.value=value
  for(const job of value){if(active(job))waiting.add(job.action);else waiting.delete(job.action)}
  if(completed)emit('completed')
}})
function time(value?:string|null){if(!value)return '—';return new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(new Date(value))}
function schedule(){if(timer)clearTimeout(timer);if(!disposed && (jobs.value.some(job=>active(job)||job.next_allowed_at)||error.value))timer=setTimeout(()=>{if(document.hidden)schedule();else refresh()},error.value?15000:3000)}
async function refresh(){error.value='';await loader.load(signal=>fetchMaintenanceJobs(signal));schedule()}
async function start(job:MaintenanceJob){if(submitting.value || !job.can_start)return;submitting.value=job.action;notice.value='';error.value='';try{const result=await startMaintenance(job.action);if(disposed)return;if(result.accepted || active(result.job))waiting.add(job.action);jobs.value=jobs.value.map(row=>row.action===job.action?result.job:row);notice.value=result.accepted?'任务已提交；完成情况以执行记录为准。':'已复用正在执行或刚提交的任务，请查看执行状态。';await refresh()}catch(e:any){if(!disposed){error.value=typeof e?.response?.data?.detail==='string'?e.response.data.detail:'提交结果尚未确认，请刷新执行状态后再操作。';schedule()}}finally{if(!disposed)submitting.value=''}}
onMounted(refresh)
onUnmounted(()=>{disposed=true;if(timer)clearTimeout(timer);loader.dispose()})
</script>
<style scoped>
.maintenance-panel{padding:22px;border:1px solid #263449;border-radius:12px;background:#111a2b;min-width:0}header,.row{display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap}header{align-items:flex-start;margin-bottom:16px}h2{font-size:16px;margin:0;color:#e2e8f0}h3{font-size:14px;margin:0;color:#e2e8f0}p{font-size:12px;line-height:1.8;color:#a8b5c9;overflow-wrap:anywhere}header p{margin-bottom:0}.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}article{min-width:0;border:1px solid #253248;border-radius:9px;background:#0c1423;padding:18px}strong{font-size:11px;color:#94a3b8;font-weight:500}.success,.skipped,.notice{color:#6ee7b7}.running,.queued{color:#7dd3fc}.partial,.unknown,.interrupted{color:#fcd38b}.error{color:#fca5a5}.message{color:#d0dae8}.counts{font-size:11px}small{display:block;font-size:11px;color:#94a3b8;line-height:1.8}button{border:1px solid #37516c;border-radius:6px;padding:8px 12px;color:#bfdbfe;background:#15243a;font-size:12px;cursor:pointer}button:disabled{opacity:.45;cursor:default}.start{margin:14px 0 9px}details{border-top:1px solid #263449;padding-top:10px;margin-top:12px}summary{font-size:11px;cursor:pointer;color:#93b5da}@media(max-width:1000px){.cards{grid-template-columns:1fr}}
</style>
