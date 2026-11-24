<template>
  <div class="observation-assistant">
    <div class="rule-heading"><strong>条件核对</strong><span v-if="entry" class="state" :class="entry.evaluation.status">{{ entry.evaluation.label }}</span><button :disabled="!!working || !entry" @click="openRule">{{ entry?.rule ? '补充规则版本' : '确认量化条件' }}</button><button v-if="entry?.rule" :disabled="!!working" @click="toggleHistory">规则历史</button></div>
    <template v-if="entry">
      <p v-if="entry.rule">{{ entry.rule.description }}</p><p v-else class="muted">保留文字条件；确认量化规则后，才会检查收盘价是否满足条件。</p>
      <small v-if="entry.rule">所属复盘日 {{ entry.rule.effective_date }} · 实际确认 {{ time(entry.rule.created_at) }} · 事后补充不代表事前已确定</small>
      <p class="muted">{{ entry.evaluation.message }}<template v-if="entry.rule && entry.evaluation.expected_samples != null"> 报价覆盖 {{ entry.evaluation.valid_samples }} / {{ entry.evaluation.expected_samples }} 个后续交易日。</template></p>
      <p v-if="entry.evaluation.first_violation" class="warning">首次不满足条件：{{ entry.evaluation.first_violation }}</p>
      <p v-if="entry.rule && entry.evaluation.missing_dates.length" class="warning">缺少报价：{{ entry.evaluation.missing_dates.slice(0,8).join('、') }}{{ entry.evaluation.missing_dates.length>8?' 等 '+entry.evaluation.missing_dates.length+' 日':'' }}</p>
    </template>
    <p v-else class="muted">条件及审阅状态正在核对，尚未取得状态时不能生成审阅。</p>
    <form v-if="ruleOpen" class="rule-form" @submit.prevent="saveRule">
      <fieldset :disabled="!!working"><legend>{{ entry?.rule ? '追加新版本，旧版本继续保留' : '将部分文字条件确认为价格规则' }}</legend>
        <div class="rule-inputs"><label>核对方式<select v-model="form.kind"><option value="end_change">期限日收盘涨跌幅</option><option value="hold_change">期间每个交易日收盘涨跌幅</option></select></label><label>相对关注日收盘<select v-model="form.operator"><option value="ge">不低于</option><option value="le">不高于</option></select></label><label>涨跌幅 %<input type="number" v-model="form.threshold_pct" min="-100" max="1000" step="0.0001" required /></label></div>
        <p class="muted">期限 {{ observation.deadline }}；休市期限取此前最后一个交易日。期间规则不含关注日；不检查盘中价格。</p>
        <label>对应原条件或本次调整原因<textarea v-model="form.note" maxlength="500" rows="2" required placeholder="这条价格规则对应原判断中的哪部分？调整规则时说明原因。"></textarea></label>
        <label class="confirmation"><input type="checkbox" v-model="confirmed" required /> 我确认这条规则仅核对价格条件；它不会替换原始理由，也不能证明整体判断正确。</label>
        <div class="actions"><button type="submit" :disabled="!confirmed">{{ working==='rule'?'保存中…':'确认并保存规则' }}</button><button type="button" @click="ruleOpen=false">取消</button></div>
      </fieldset>
    </form>
    <div v-if="historyOpen" class="history"><strong>截至 {{ date }} 的规则版本</strong><p v-if="historyLoading" class="muted">正在读取…</p><article v-for="rule in history" :key="rule.id"><p>{{ rule.description }}</p><small>所属 {{ rule.effective_date }} · 实际保存 {{ time(rule.created_at) }}</small><p>{{ rule.note }}</p></article></div>
    <div class="ai-heading"><div><strong>AI 审阅</strong><small>独立意见，引用所选日证据；由你决定是否补充人工验证。</small></div><div class="actions"><button :disabled="!!working || !entry || !ai?.configured" @click="runAudit(false)">{{ working==='ai'?'正在审阅，请稍候…':'审阅当前资料' }}</button><button v-if="audit" :disabled="!!working || !entry || !ai?.configured" @click="runAudit(true)">重新生成</button><button :disabled="!!working" @click="toggleAuditHistory">{{ auditHistoryOpen?'收起审阅历史':'审阅历史' }}</button></div></div>
    <div v-if="auditHistoryOpen" class="history"><strong>截至 {{ date }} 的历史审阅</strong><p v-if="auditHistoryLoading" class="muted">正在读取…</p><template v-else-if="auditHistory"><p v-if="!auditHistory.items.length" class="muted">还没有保存的 AI 审阅。</p><div v-for="item in auditHistory.items" :key="item.id" class="audit-history-row"><span>依据 {{ item.date }} · 实际生成 {{ time(item.created_at) }} · {{ item.model }}</span><button @click="viewSavedAudit(item.id)">{{ audit?.id===item.id?'当前查看':'查看这份意见' }}</button></div><div v-if="auditHistory.pages>1" class="actions"><button :disabled="auditHistory.page<=1" @click="loadAuditHistory(auditHistory.page-1)">上一页</button><small>{{ auditHistory.page }} / {{ auditHistory.pages }}</small><button :disabled="auditHistory.page>=auditHistory.pages" @click="loadAuditHistory(auditHistory.page+1)">下一页</button></div></template></div>
    <small v-if="!ai?.configured">AI 服务尚未配置，条件核对和提醒可继续使用。</small>
    <p v-if="notice" class="notice" role="status">{{ notice }}</p><p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="snapshotLoading" class="muted">正在读取保存的意见与原始证据…</p>
    <div v-if="audit&&!snapshotLoading" class="audit-result">
      <p v-if="audit.historical" class="warning">这是依据 {{ audit.date }} 资料生成的历史意见；引用仍是保存时的证据，不将它当作 {{ date }} 的新判断。</p>
      <p v-else-if="audit.stale" class="warning">规则、验证或行情已变化，这份意见已过期。保留旧证据供核对，需重新审阅当前资料。</p>
      <div v-if="audit.changes.length" class="changes"><strong>这次查看与上次审阅相比</strong><p v-for="change in audit.changes" :key="change">· {{ change }}</p></div>
      <p v-else-if="audit.historical" class="muted">暂未发现新增可核对资料；历史日期与生成时间见下方。</p>
      <button v-if="selectedAudit && entry?.audit && selectedAudit.id!==entry.audit.id" @click="selectedAudit=null">返回最近一次审阅</button>
      <small>依据截至 {{ audit.date }} 的资料 · 实际生成 {{ time(audit.created_at) }} · {{ audit.model }}</small>
      <div class="audit-grid"><section v-for="group in groups" :key="group.key"><h4>{{ group.label }}</h4><template v-if="audit.result[group.key].length"><div v-for="(item,index) in audit.result[group.key]" :key="index" class="audit-item"><p>{{ item.text }}</p><details><summary>引用 {{ item.evidence_ids.length }} 条资料</summary><div v-for="fact in cited(item)" :key="fact.id" class="fact"><b>{{ fact.label }}</b><p>{{ factText(fact) }}</p></div></details></div></template><p v-else class="muted">未列出相关意见。</p></section></div>
      <small>以上是模型对所列资料的审阅意见，未进行外部新闻核验；事实、推断与人工结论请分别核对。</small>
    </div>
    <p v-else class="muted">首次点击会发送这一条关注的理由、验证及引用行情进行审阅。打开页面不会自动调用 AI。</p>
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, reactive, ref, watch } from 'vue'
import { auditReviewObservation, confirmReviewCondition, fetchReviewConditions, fetchReviewAuditHistory, fetchSavedReviewAudit } from '../../api/client'
import type { ReviewAssistantData, ReviewAssistantEntry, ReviewAudit, ReviewAuditHistory, ReviewAuditItem, ReviewCondition, ReviewFact, ReviewObservation } from '../../api/client'
import { createLatestLoader } from '../../utils/latestLoader'
const props=defineProps<{date:string;observation:ReviewObservation;entry?:ReviewAssistantEntry;ai?:ReviewAssistantData['ai']}>()
const emit=defineEmits<{changed:[]}>()
const working=ref(''),notice=ref(''),error=ref(''),ruleOpen=ref(false),confirmed=ref(false),historyOpen=ref(false),historyLoading=ref(false),history=ref<ReviewCondition[]>([]),localAudit=ref<ReviewAudit|null>(null)
const form=reactive({kind:'hold_change',operator:'ge',threshold_pct:'0',note:''})
const auditHistoryOpen=ref(false),auditHistory=ref<ReviewAuditHistory|null>(null),auditHistoryLoading=ref(false),selectedAudit=ref<ReviewAudit|null>(null),snapshotLoading=ref(false)
let disposed=false,generation=0,request:AbortController|null=null
const audit=computed(()=>selectedAudit.value || (props.entry?.audit && props.entry.audit.id >= (localAudit.value?.id || 0) ? props.entry.audit : localAudit.value))
const groups:{key:keyof ReviewAudit['result'];label:string}[]=[{key:'supporting_evidence',label:'支持证据'},{key:'counter_evidence',label:'相反证据'},{key:'uncertainties',label:'尚不能确认'},{key:'next_checks',label:'下一次验证'}]
const historyLoader=createLatestLoader<ReviewCondition[]>({resolve:value=>history.value=value,reject:()=>error.value='规则历史读取失败，请重试。',pending:value=>historyLoading.value=value})
const auditHistoryLoader=createLatestLoader<ReviewAuditHistory>({resolve:value=>auditHistory.value=value,reject:()=>error.value='审阅历史读取失败，请重试。',pending:value=>auditHistoryLoading.value=value})
const snapshotLoader=createLatestLoader<ReviewAudit>({resolve:value=>selectedAudit.value=value,reject:()=>error.value='历史意见读取失败，请重试。',pending:value=>snapshotLoading.value=value})
function loadAuditHistory(page=1){error.value='';return auditHistoryLoader.load(signal=>fetchReviewAuditHistory(props.observation.id,props.date,page,signal))}
function toggleAuditHistory(){auditHistoryOpen.value=!auditHistoryOpen.value;if(auditHistoryOpen.value)loadAuditHistory()}
function viewSavedAudit(id:number){error.value='';return snapshotLoader.load(signal=>fetchSavedReviewAudit(props.observation.id,id,props.date,signal))}
function time(value:string){return new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}).format(new Date(value))}
function openRule(){const old=props.entry?.rule;form.kind=old?.kind||'hold_change';form.operator=old?.operator||'ge';form.threshold_pct=old?.threshold_pct||'0';form.note=old?'':props.observation.criterion.slice(0,500);confirmed.value=false;ruleOpen.value=true;error.value=''}
async function toggleHistory(){historyOpen.value=!historyOpen.value;if(historyOpen.value)await historyLoader.load(signal=>fetchReviewConditions(props.observation.id,props.date,signal))}
async function saveRule(){
  if(working.value||!confirmed.value)return
  const current=generation;working.value='rule';notice.value='';error.value=''
  try{await confirmReviewCondition(props.observation.id,{...form,effective_date:props.date,threshold_pct:String(form.threshold_pct)});if(disposed||generation!==current)return;ruleOpen.value=false;historyOpen.value=false;if(localAudit.value)localAudit.value.stale=true;notice.value='规则版本已保存，原始关注和旧版本继续保留。';emit('changed')}
  catch(e:any){if(!disposed&&generation===current)error.value=typeof e?.response?.data?.detail==='string'?e.response.data.detail:'规则保存结果尚未确认，请刷新核对。'}
  finally{if(current===generation)working.value=''}
}
async function runAudit(force:boolean){
  if(working.value||!props.entry||!props.ai?.configured)return
  const current=generation;request?.abort();request=new AbortController();working.value='ai';notice.value='';error.value=''
  try{const result=await auditReviewObservation(props.observation.id,props.date,force,request.signal);if(disposed||generation!==current)return;selectedAudit.value=null;localAudit.value=result;notice.value=result.cached?'证据未变化，已复用保存的审阅结果。':'AI 审阅已保存，人工验证结论未被修改。';emit('changed')}
  catch(e:any){if(!disposed&&generation===current)error.value=e?.response?.data?.detail||'审阅结果尚未确认，请刷新查看是否已保存；避免立即重复提交。'}
  finally{if(current===generation)working.value=''}
}
function cited(item:ReviewAuditItem){return audit.value?.facts.filter(f=>item.evidence_ids.includes(f.id))||[]}
const labels:Record<string,string>={code:'股票代码',date:'日期',reason:'原始理由',criterion:'原始条件',deadline:'期限',recorded_at:'实际录入',description:'规则',note:'确认说明',effective_date:'所属复盘日',created_at:'实际确认',label:'核对状态',expected_samples:'应有交易日',valid_samples:'有效报价日',missing_dates:'缺失日期',first_violation:'首次不满足',end_date:'核对截止交易日',end_change_pct:'截止涨跌幅 %',message:'核对说明',verdict:'人工结论',explanation:'人工依据',up:'上涨家数',down:'下跌家数',limit_up:'涨停家数',limit_down:'跌停家数',turnover:'全市场成交额'}
function factText(fact:ReviewFact){if(fact.value===null||typeof fact.value!=='object')return String(fact.value??'未知');return Object.entries(fact.value as Record<string,unknown>).filter(([key,value])=>labels[key]&&value!==null&&value!==undefined).map(([key,value])=>`${labels[key]}：${Array.isArray(value)?value.join('、')||'无':String(value)}`).join('\n')}
watch(()=>[props.date,props.observation.id],()=>{generation++;request?.abort();historyLoader.cancel();auditHistoryLoader.cancel();snapshotLoader.cancel();selectedAudit.value=null;auditHistory.value=null;auditHistoryOpen.value=false;localAudit.value=null;history.value=[];historyOpen.value=false;ruleOpen.value=false;working.value='';error.value='';notice.value=''})
watch(()=>[props.observation.verdict,props.observation.explanation],()=>{if(localAudit.value)localAudit.value.stale=true})
onUnmounted(()=>{disposed=true;generation++;request?.abort();historyLoader.dispose();auditHistoryLoader.dispose();snapshotLoader.dispose()})
</script>

<style scoped>
.audit-history-row{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;padding:12px 0;border-bottom:1px solid #29364b;font-size:12px;color:#a5b4c8}.changes{border-left:2px solid #6285b5;padding:8px 12px;margin:12px 0;background:#15243a;font-size:12px;color:#bfdbfe}.changes p{margin:5px 0}
.observation-assistant{border-top:1px solid #29364b;margin-top:18px;padding-top:16px;color:#cbd5e1;font-size:13px}.rule-heading,.ai-heading,.actions,.rule-inputs{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.rule-heading strong,.ai-heading strong{color:#e5e7eb}.ai-heading{justify-content:space-between;border-top:1px solid #263449;margin-top:18px;padding-top:16px}.ai-heading small{display:block}.state{font-size:12px;border-radius:4px;padding:4px 7px;background:#1f2937;color:#cbd5e1}.state.not_met{background:#422006;color:#fcd34d}.state.met{background:#14372d;color:#a7f3d0}.state.unknown{color:#fcd34d}.muted,small{font-size:12px;color:#9ca3af;line-height:1.9}p{line-height:1.9;white-space:pre-wrap;overflow-wrap:anywhere}button,input,select,textarea{border:1px solid #3b4a60;border-radius:6px;background:#111c2d;color:#d1d5db;padding:7px 10px;font-size:12px}button{cursor:pointer}button:disabled{opacity:.4;cursor:default}.rule-form{padding:15px;background:#101d30;border-radius:8px;margin:14px 0}fieldset{border:0;padding:0;min-width:0}legend{font-size:12px;margin-bottom:14px;color:#93c5fd}label{font-size:12px;line-height:1.8}label select,label input{display:block;margin-top:5px}.rule-inputs input{max-width:100px}textarea{display:block;width:100%;box-sizing:border-box;margin:8px 0 12px;resize:vertical;line-height:1.8}.confirmation{display:flex;align-items:flex-start;gap:8px;color:#cbd5e1;margin-bottom:14px}.confirmation input{margin:5px 0}.warning,.notice{color:#fcd34d;font-size:12px}.error{color:#fca5a5;font-size:12px}.history{background:#111b2a;padding:14px;border-radius:6px}.history article{border-top:1px solid #2b374a;margin-top:12px}.audit-result{background:#101b2b;border:1px solid #2d405c;padding:16px;margin-top:14px;border-radius:8px}.audit-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin:12px 0}h4{font-size:13px;color:#93c5fd;margin:8px 0}.audit-item{margin-bottom:14px}.audit-item p{margin:6px 0}.audit-item details{font-size:12px;color:#9ca3af}.audit-item summary{cursor:pointer;color:#93aaca}.fact{border-left:2px solid #394c68;padding-left:10px;margin-top:10px}.fact b{font-size:12px;color:#cbd5e1}.fact p{white-space:pre-wrap;font-size:12px;max-height:240px;overflow:auto}@media(max-width:750px){.audit-grid{grid-template-columns:1fr}.ai-heading{align-items:flex-start}.rule-inputs{align-items:flex-start;flex-direction:column}}
</style>
