<template>
  <section class="assistant-panel" aria-label="复盘提醒">
    <header><div><span class="eyebrow">先处理与你有关的事项</span><h2>待验证与审阅提醒 <b v-if="data">{{ data.active_count }}</b></h2></div><button :disabled="loading" @click="load">刷新提醒</button></header>
    <p class="muted">按 {{ date }} 核对全部未完成关注，并检查已有价格规则的通过结论。原始理由与人工结论继续保留。</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <div class="toolbar"><span v-if="data" class="ai-state">{{ data.ai.configured ? 'AI 审阅可用 · '+data.ai.model : 'AI 审阅尚未配置' }}</span><label><input type="checkbox" v-model="includeHidden" /> 查看已读与暂缓事项</label><small v-if="data">待验证 {{ data.pending_count }} 条 · 核查范围 {{ data.scope_count }} 条</small></div>
    <p v-if="loading" class="muted">正在核对本地关注记录…</p>
    <template v-else-if="data">
      <div v-for="item in data.reminders" :key="item.key" class="reminder" :class="[item.level,{hidden:item.hidden}]">
        <div class="reminder-body"><button class="stock-link" @click="$emit('focus',item.observation_id)">{{ item.name }} {{ item.code }}</button><strong>{{ item.title }}</strong><p>{{ item.message }}</p><small v-if="item.hidden">{{ item.snooze_until ? '暂缓至 '+item.snooze_until : '已读；新的条件反例仍会单独提醒' }}</small></div>
        <div class="actions"><button @click="$emit('focus',item.observation_id)">查看关注</button><template v-if="!item.hidden"><button :disabled="!!working" @click="act(item,'read')">已读</button><button :disabled="!!working" @click="act(item,'snooze')">次日再提醒</button></template><button v-else :disabled="!!working" @click="act(item,'reset')">恢复提醒</button></div>
      </div>
      <p v-if="!data.reminders.length" class="empty">{{ data.scope_count ? '当前没有未处理提醒。仍可在关注清单中查看历史意见或主动审阅。' : '添加一条关注及验证期限后，这里会集中显示需要处理的事项。' }}</p>
      <div v-if="data.pages>1" class="pagination"><button :disabled="data.page<=1 || loading" @click="go(data.page-1)">上一页</button><span>{{ data.page }} / {{ data.pages }} · {{ data.total }} 条提醒</span><button :disabled="data.page>=data.pages || loading" @click="go(data.page+1)">下一页</button></div>
      <small class="footnote">{{ data.ai.message }} 价格核对使用未复权收盘价，缺失数据保留为未知。</small>
    </template>
  </section>
</template>
<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { fetchReviewAssistant, updateReviewReminder } from '../../api/client'
import type { ReviewAssistantData, ReviewReminder } from '../../api/client'
import { createLatestLoader } from '../../utils/latestLoader'
const props=defineProps<{date:string;revision:number}>()
defineEmits<{focus:[id:number]}>()
const data=ref<ReviewAssistantData|null>(null),loading=ref(false),error=ref(''),notice=ref(''),working=ref(''),includeHidden=ref(false),page=ref(1)
let generation=0,disposed=false
const loader=createLatestLoader<ReviewAssistantData>({resolve:value=>{data.value=value;page.value=value.page},reject:()=>{data.value=null;error.value='提醒读取失败，请刷新重试。'},pending:value=>loading.value=value})
function load(){error.value='';return loader.load(signal=>fetchReviewAssistant(props.date,signal,{page:page.value,include_hidden:includeHidden.value}))}
function go(value:number){page.value=value;load()}
async function act(item:ReviewReminder,action:'read'|'snooze'|'reset'){
  if(working.value)return
  const current=generation,date=props.date
  working.value=item.key;notice.value=''
  const tomorrow=new Date(date+'T00:00:00Z');tomorrow.setUTCDate(tomorrow.getUTCDate()+1)
  try{await updateReviewReminder(item.key,date,action,action==='snooze'?tomorrow.toISOString().slice(0,10):undefined);if(disposed||current!==generation)return;notice.value=action==='snooze'?'已暂缓至所选复盘日期的次日。':action==='read'?'已标记为已读。':'已恢复提醒。';await load()}
  catch(e:any){if(!disposed&&current===generation)notice.value=e?.response?.data?.detail||'处理结果尚未确认，请刷新查看。'}
  finally{if(current===generation)working.value=''}
}
watch(()=>[props.date,props.revision,includeHidden.value],(value,old)=>{generation++;working.value='';notice.value='';if(!old||value[0]!==old[0]||value[2]!==old[2])page.value=1;data.value=null;load()},{immediate:true})
onUnmounted(()=>{disposed=true;generation++;loader.dispose()})
</script>
<style scoped>
.assistant-panel{border:1px solid #344a67;border-radius:14px;padding:22px;background:linear-gradient(115deg,#122239,#111827);margin:22px 0;font-size:13px}header,.toolbar,.actions,.pagination{display:flex;align-items:center;gap:12px;flex-wrap:wrap}header{justify-content:space-between}.eyebrow{color:#93c5fd;font-size:12px}h2{font-size:19px;color:#f3f4f6;margin:8px 0}h2 b{font-size:13px;background:#243d60;border-radius:14px;padding:3px 9px;margin-left:6px}.muted,small,.footnote{color:#9ca3af;line-height:1.8}.toolbar{border-block:1px solid #2a3a50;padding:12px 0;margin:16px 0}.ai-state{color:#bfdbfe}.toolbar label{display:flex;align-items:center;gap:6px;color:#cbd5e1}.reminder{display:flex;align-items:center;justify-content:space-between;gap:18px;background:#0d1727;border-radius:8px;border-left:3px solid #48607e;padding:16px;margin-top:10px}.reminder.warning{border-left-color:#fb923c}.reminder.attention{border-left-color:#facc15}.reminder.hidden{opacity:.65}.reminder strong{color:#e5e7eb;font-size:13px}.reminder p{color:#cbd5e1;line-height:1.8;margin:7px 0}.stock-link{border:0;padding:0;margin-right:12px;color:#93c5fd;background:transparent;font-weight:600}button{border:1px solid #374b65;background:#132034;border-radius:6px;padding:7px 11px;color:#dbeafe;cursor:pointer;font-size:12px}button:disabled{opacity:.4;cursor:default}.actions{flex-shrink:0;gap:7px}.footnote{display:block;margin-top:14px;font-size:12px}.error{color:#fca5a5}.notice{color:#fcd34d}.empty{color:#9ca3af;text-align:center;padding:18px;line-height:1.8}.pagination{justify-content:center;margin-top:18px;color:#9ca3af}@media(max-width:700px){.assistant-panel{padding:16px}.reminder{align-items:flex-start;flex-direction:column}.actions{flex-wrap:wrap}}
</style>
