<template>
  <main class="workbench">
    <header class="heading"><div><small>验证过去 / 记录依据 / 追踪变化</small><h1>复盘工作台</h1><p>先看昨天的强势今天怎样，再留下你自己的判断。</p></div><div class="controls"><button :disabled="!previousDate || loading" @click="load(previousDate)">◀ 前一日</button><input aria-label="复盘日期" type="date" :value="data?.date" :max="today" @change="changeDate" /><button :disabled="loading" @click="load()">最新数据</button><button :disabled="loading" @click="load(data?.date)">刷新</button></div></header>
    <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="loading" class="empty">正在整理复盘资料…</p>
    <template v-if="data && !loading">
      <div class="status">复盘日期 {{ data.date }} · 对比 {{ data.previous_date || '暂无更早记录' }}<span> · 对比日为前一个已入库统计日</span></div>
      <ReviewAssistantPanel :date="data.date" :revision="assistantRevision" @focus="observationsRef?.focus($event)" />
      <section class="panel summary"><h2>昨天的强势，今天的结果</h2><p v-if="!data.performance.ready" class="notice">当日或对比日涨停明细尚未齐备，延续率留空；报价缺失显示未知，不按下跌计算。</p><p v-else>对比日涨停 {{ data.performance.stats.total }} 家，其中 {{ data.performance.stats.promoted }} 家继续涨停，延续率 {{ percent(data.performance.stats.promote_rate) }}。</p><p>今日有效报价 {{ data.performance.stats.quote_samples }} / {{ data.performance.stats.total }} 家；平均涨幅 {{ percent(data.performance.stats.avg_pct) }}，中位涨幅 {{ percent(data.performance.stats.median_pct) }}。</p><div class="market-context" v-if="data.snapshot">市场背景：上涨占比 {{ percent(data.snapshot.up_ratio) }} · 涨停 {{ data.snapshot.limit_up }} / 跌停 {{ data.snapshot.limit_down }} · 炸板率 {{ percent(data.snapshot.break_rate) }}</div></section>
      <div class="metrics"><article v-for="group in data.performance.groups" :key="group.label"><span>{{ group.label }}</span><strong>{{ number(group.continued) }} / {{ group.total }}</strong><small>延续率 {{ percent(group.rate) }}</small></article><article><span>今日首板 / 二板 / 三板及以上</span><strong>{{ number(data.structure.first) }} / {{ number(data.structure.second) }} / {{ number(data.structure.higher) }}</strong><small>最高 {{ number(data.structure.highest) }} 板</small></article></div>
      <details id="emotion" ref="emotionSection" class="panel emotion-panel" :open="emotionOpen" @toggle="emotionOpen=($event.target as HTMLDetailsElement).open">
        <summary><strong>情绪与阶段走势</strong><span>截至 {{ data.date }} · 展开查看最近一月至全部历史</span></summary>
        <EmotionHistory v-if="emotionOpen" :as-of="data.date" :range-days="emotionRange" @range-change="emotionRange=$event" @select-date="load" />
      </details>
      <section class="panel"><div class="section-header"><h2>对比日最高板的去向</h2><router-link :to="{name:'overview',query:{tab:'ladder',date:data.date}}">在概览查看当日连板天梯 →</router-link></div><p v-if="!data.performance.leaders.length" class="empty">暂无可比的最高板记录</p><div class="leaders"><button v-for="item in data.performance.leaders" :key="item.code" @click="open(item.code,item.name)"><b>{{ item.name }}</b><span>原 {{ item.prev_boards }} 板 → {{ item.status }}<template v-if="item.today_boards"> {{ item.today_boards }} 板</template></span><strong :class="tone(item.today_pct)">{{ percent(item.today_pct) }}</strong></button></div></section>
      <section class="panel"><div class="section-header"><h2>强势股验证明细</h2><div class="controls"><select v-model="outcome"><option value="">所有结果</option><option v-for="s in ['晋级','炸板','跌停','红盘','绿盘','平盘','未知']" :key="s">{{ s }}</option></select><select v-model.number="boards"><option :value="0">所有层级</option><option :value="1">原首板</option><option :value="2">原二板</option><option :value="3">原三板及以上</option></select></div></div><div class="table-wrap"><table><thead><tr><th>股票</th><th>对比日层级</th><th>今日结果</th><th>今日涨幅</th><th>操作</th></tr></thead><tbody><tr v-for="item in filtered.slice(0,expanded?undefined:20)" :key="item.code"><td><button class="link" @click="open(item.code,item.name)">{{ item.name }} <small>{{ item.code }}</small></button></td><td>{{ item.prev_boards }} 板</td><td>{{ item.status }} {{ item.today_boards ? item.today_boards+'板' : '' }}</td><td :class="tone(item.today_pct)">{{ percent(item.today_pct) }}</td><td><button @click="observationsRef?.prefillStock(item.code); observationSection?.scrollIntoView({behavior:'smooth'})">关注</button></td></tr></tbody></table></div><p v-if="!filtered.length" class="empty">暂无匹配记录</p><button v-if="filtered.length>20" @click="expanded=!expanded">{{ expanded?'收起':'展开全部 '+filtered.length+' 条' }}</button></section>
      <div ref="observationSection"><ReviewObservations ref="observationsRef" :date="data.date" :revision="assistantRevision" @saved="refreshObservations" @open="open" /></div>
      <section class="panel"><div class="section-header"><div><h2>当日记录与后续关注</h2><small>事实已列在上方，只需补充判断。草稿按日期保存在当前浏览器，点击保存后写入服务器。</small></div><router-link :to="{path:'/review/journal',query:{date:data.date}}">交易台账与历史笔记 →</router-link></div><p v-if="noteMessage" class="notice" role="status">{{ noteMessage }}</p><textarea aria-label="当日复盘笔记" v-model="note" :disabled="!noteReady" rows="9" placeholder="今天最重要的变化是什么？原来的判断需要怎样修正？下一交易日具体观察什么？"></textarea><div class="controls"><button @click="insertTemplate" :disabled="!noteReady">插入事实与提问模板</button><button @click="save" :disabled="saving || !noteReady">{{ saving?'保存中…':'保存复盘' }}</button><span>{{ dirty ? '有尚未提交的修改' : '与服务器内容一致' }}</span></div><div v-if="dayTrades.length" class="day-trades"><h3>已录入的当日交易</h3><p v-for="trade in dayTrades" :key="trade.id">{{ trade.name || trade.code }} · {{ trade.direction==='buy'?'买入':'卖出' }} {{ trade.quantity }} 股 × {{ trade.price }} · {{ trade.note || '尚未记录操作依据' }}</p></div><p v-else class="note">当日没有已录入交易；不影响使用自动复盘。</p></section>
    </template>
    <PigletStockDetailPopup :visible="detail.visible" :code="detail.code" :name="detail.name" :as-of="data?.date" @close="detail.visible=false" />
  </main>
</template>
<script setup lang="ts">
import { computed,nextTick,onMounted,onUnmounted,reactive,ref,watch } from 'vue'
import { onBeforeRouteLeave,useRoute } from 'vue-router'
import { fetchReviewWorkbench,fetchNote,saveNote,fetchJournalTrades } from '../api/client'
import type { ReviewWorkbenchData,JournalTrade } from '../api/client'
import ReviewObservations from '../components/review/ReviewObservations.vue'
import ReviewAssistantPanel from '../components/review/ReviewAssistantPanel.vue'
import EmotionHistory from '../components/review/EmotionHistory.vue'
import PigletStockDetailPopup from '../components/strategy/PigletStockDetailPopup.vue'
const route=useRoute(),data=ref<ReviewWorkbenchData|null>(null),loading=ref(false),error=ref('')
const assistantRevision=ref(0),observationsRef=ref<InstanceType<typeof ReviewObservations>|null>(null)
const emotionOpen=ref(route.query.section === 'emotion' || route.hash === '#emotion')
const emotionSection=ref<HTMLDetailsElement|null>(null),emotionRange=ref(29)
const outcome=ref(''),boards=ref(0),expanded=ref(false),observationSection=ref<HTMLElement|null>(null)
const detail=reactive({visible:false,code:'',name:''}),note=ref(''),serverNote=ref(''),noteReady=ref(false),noteMessage=ref(''),saving=ref(false),draftFailed=ref(false),dayTrades=ref<JournalTrade[]>([]),noteCodes=ref<string[]>([])
const today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date())
const serverCodes=ref('')
let controller:AbortController|null=null
const dirty=computed(()=>note.value!==serverNote.value || noteCodes.value.join(',')!==serverCodes.value)
const previousDate=computed(()=>[...(data.value?.available_dates || [])].reverse().find(d=>d<(data.value?.date || '')) || '')
const filtered=computed(()=>data.value?.performance.items.filter(r=>(!outcome.value||r.status===outcome.value)&&(!boards.value||(boards.value===3?r.prev_boards>=3:r.prev_boards===boards.value))) || [])
function number(v:number|null){return v==null?'—':v}
function percent(v:number|null){return v==null?'—':`${v>0?'+':''}${v.toFixed(1)}%`}
function tone(v:number|null){return v==null||v===0?'':v>0?'up':'down'}
function open(code:string,name:string){detail.code=code;detail.name=name;detail.visible=true}
function draftKey(date:string){return `stocks_review_draft_v2:${date}`}
function preserveDraft(){if(!noteReady.value||!data.value)return;try{if(dirty.value)localStorage.setItem(draftKey(data.value.date),JSON.stringify({content:note.value,codes:noteCodes.value.join(',')}));else localStorage.removeItem(draftKey(data.value.date));draftFailed.value=false}catch{draftFailed.value=true;noteMessage.value='浏览器草稿保存失败，请先保存到服务器再离开。'}}
watch(note,preserveDraft,{flush:'sync'})
async function load(date?:string){
 if(dirty.value&&draftFailed.value&&!confirm('草稿未能保存，确定切换日期吗？'))return
 controller?.abort();const request=new AbortController();controller=request;loading.value=true;error.value='';noteReady.value=false;detail.visible=false
 try{const result=await fetchReviewWorkbench(date,request.signal);if(request.signal.aborted)return;data.value=result;noteMessage.value='';
  const [saved,trades]=await Promise.all([fetchNote(result.date),fetchJournalTrades(undefined,result.date,result.date)])
  if(request.signal.aborted)return;serverNote.value=saved.content;note.value=saved.content;noteCodes.value=saved.codes;serverCodes.value=saved.codes.join(',');dayTrades.value=trades
  try{const draft=JSON.parse(localStorage.getItem(draftKey(result.date))||'null');if(typeof draft?.content==='string'&&(draft.content!==saved.content || (typeof draft.codes==='string' && draft.codes!==serverCodes.value))){note.value=draft.content;if(typeof draft.codes==='string')noteCodes.value=draft.codes.split(/[,\s]+/).filter(Boolean);noteMessage.value='已恢复此日期的浏览器草稿，请检查后保存。'}}catch{noteMessage.value='草稿读取失败，当前显示服务器笔记。'}noteReady.value=true
 }catch(e:any){if(!request.signal.aborted){error.value=e?.response?.data?.detail||'加载复盘失败，请重试';noteMessage.value='笔记未加载成功，已禁用编辑以避免覆盖。'}}finally{if(controller===request)loading.value=false}
}
function changeDate(event:Event){const date=(event.target as HTMLInputElement).value;if(date)load(date)}
function refreshObservations(){assistantRevision.value++}
async function save(){if(!data.value)return;const date=data.value.date,content=note.value,codes=[...noteCodes.value];saving.value=true;try{await saveNote(date,content,codes);if(data.value?.date===date){serverNote.value=content;serverCodes.value=codes.join(',');preserveDraft();noteMessage.value=dirty.value?'已保存提交时的版本，后续修改仍为草稿。':'已保存到服务器。'}}catch{noteMessage.value='保存失败，草稿仍保留在浏览器。'}finally{saving.value=false}}
function insertTemplate(){if(!data.value)return;const d=data.value;note.value += `${note.value?'\n\n':''}【${d.date} 已入库事实】\n对比日：${d.previous_date || '未知'}\n强势股今日平均/中位涨幅：${percent(d.performance.stats.avg_pct)} / ${percent(d.performance.stats.median_pct)}\n有效报价：${d.performance.stats.quote_samples}/${d.performance.stats.total}\n\n【今天最重要的变化】\n\n【原判断需要怎样修正】\n\n【下一交易日具体观察什么】\n`}
onBeforeRouteLeave(()=>!(dirty.value&&draftFailed.value)||confirm('草稿保存失败，确定离开吗？'))
async function showEmotion(){emotionOpen.value=true;await nextTick();emotionSection.value?.scrollIntoView({behavior:'smooth',block:'start'})}
watch(()=>[route.query.date,route.query.section,route.hash],async()=>{
  const date=typeof route.query.date==='string'?route.query.date:undefined
  if(date && date!==data.value?.date)await load(date)
  if(route.query.section==='emotion'||route.hash==='#emotion')await showEmotion()
})
onMounted(async()=>{await load(typeof route.query.date==='string'?route.query.date:undefined);if(emotionOpen.value)await showEmotion()})
onUnmounted(()=>controller?.abort())
</script>
<style scoped>
.emotion-panel { scroll-margin-top:20px; }.emotion-panel summary { cursor:pointer; color:#e5e7eb; font-size:15px; }.emotion-panel summary span { color:#9ca3af; font-size:12px; margin-left:14px; }

.workbench{padding:28px;max-width:1450px;margin:auto;font-variant-numeric:tabular-nums}.heading,.controls,.section-header,.leaders{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.heading,.section-header{justify-content:space-between}h1{color:#fff;font-size:28px;margin:8px 0}h2{color:#fff;font-size:17px;margin:0 0 10px}h3{font-size:14px;color:#e5e7eb}small,.status,.note{color:#9ca3af;font-size:12px;line-height:1.8}p{font-size:13px;color:#d1d5db;line-height:1.9}.heading>div>small{color:#60a5fa}.status{padding:14px 0;margin:20px 0;border-block:1px solid #253045}.panel{padding:22px;background:#111827;border:1px solid #253045;border-radius:12px;margin:22px 0}.summary{border-left:3px solid #60a5fa;background:linear-gradient(110deg,#152239,#111827)}.market-context{color:#9ca3af;font-size:12px}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px}.metrics article{padding:18px;background:#111827;border:1px solid #253045;border-radius:10px}.metrics span{font-size:12px;color:#9ca3af}.metrics strong{display:block;font-size:25px;color:#fff;margin:12px 0}button,input,select,textarea{border:1px solid #374151;border-radius:6px;background:#111827;color:#d1d5db;padding:7px 11px}button{cursor:pointer}button:disabled{opacity:.4}.leaders button{display:flex;gap:8px;flex-direction:column;align-items:flex-start;background:#0b1220;padding:16px}.leaders span{font-size:12px;color:#9ca3af}.link,a{color:#60a5fa;text-decoration:none;font-size:13px}.link{border:0;padding:0}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:13px;white-space:nowrap}td,th{text-align:left;border-bottom:1px solid #253045;padding:12px}th{color:#9ca3af;font-weight:400}td small{margin-left:6px}.up{color:#ef4444}.down{color:#22c55e}.notice{color:#fbbf24;font-size:12px}.error{color:#fca5a5;background:#450a0a;padding:12px}.empty{text-align:center;padding:24px;color:#9ca3af}textarea{width:100%;box-sizing:border-box;resize:vertical;margin:12px 0;line-height:1.8}.controls span{font-size:12px;color:#9ca3af}.day-trades{margin-top:20px}@media(max-width:650px){.workbench{padding:16px}.panel{padding:16px}}
</style>
