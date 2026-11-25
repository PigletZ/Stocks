<template>
  <section class="panel">
    <header class="section-header"><div><h2>我的关注清单</h2><small>先看状态与下一步，展开一条关注即可核对原判断、证据和历史意见。</small></div><button @click="toggleForm">{{ showForm?'收起录入':'新增关注' }}</button></header>
    <p v-if="notice" class="notice" role="status">{{ notice }}</p><p v-if="error" class="error" role="alert">{{ error }}</p>
    <form v-if="showForm" class="create-form" @submit.prevent="create">
      <fieldset :disabled="saving">
        <div class="form-grid"><label>01 / 选择股票<ReviewStockSearch v-model="form.code" :disabled="saving" /></label><label>02 / 验证模板<select v-model="preset"><option value="custom">自定义文字条件</option><option value="end_change">期限日收盘表现</option><option value="hold_change">期间收盘保持条件</option></select></label></div>
        <div class="deadline-row"><span>关注日期 {{ date }}</span><label>观察期限<select :value="duration" @change="selectDuration"><option v-for="option in deadlineOptions" :key="option.days" :value="option.days">{{ option.days }} 个交易日 · {{ option.date }}</option><option value="manual">手动选择日期</option></select></label><label>验证日期<input type="date" v-model="form.deadline" :min="date" required @input="duration='manual'" /></label><button type="button" :disabled="calendarLoading" @click="loadDeadlines">{{ calendarLoading?'读取日历中…':'更新交易日期' }}</button></div>
        <small v-if="deadlineError" class="warning">{{ deadlineError }}</small>
        <div v-if="preset!=='custom'" class="price-template"><label>相对关注日收盘<select v-model="operator"><option value="ge">涨跌幅不低于</option><option value="le">涨跌幅不高于</option></select></label><label>阈值 %<input type="number" v-model="threshold" min="-100" max="1000" step="0.0001" required /></label><p>{{ form.criterion }}</p></div>
        <label>03 / 关注理由<textarea v-model="form.reason" maxlength="2000" rows="3" required placeholder="记录当时看到的事实，以及你为何认为值得继续观察。"></textarea></label>
        <label v-if="preset==='custom'">怎样验证<textarea v-model="form.criterion" maxlength="2000" rows="2" required placeholder="哪些事实出现时算符合预期？哪些情况需要重新评估？"></textarea></label>
        <label v-else class="confirmation"><input type="checkbox" v-model="ruleConfirmed" /> 同时保存上面这条价格规则，用于自动核对；原始理由继续保留。未勾选时只记录文字条件。</label>
        <small>记录保留实际保存时间。新价格模板使用对应日期因子的复权变化；原始收盘与旧规则口径分别保留。</small>
        <div class="actions"><button class="primary" type="submit" :disabled="saving">{{ saving?'保存中…':ruleConfirmed&&preset!=='custom'?'保存关注与已确认规则':'保存关注' }}</button><button type="button" @click="showForm=false">暂时收起</button></div>
      </fieldset>
    </form>
    <div class="filters"><select aria-label="关注状态" v-model="status" @change="changeFilter"><option value="pending">待验证 / 继续观察</option><option value="due">已到验证期限</option><option value="completed">已完成验证</option><option value="all">全部记录</option></select><input v-model="search" aria-label="搜索关注记录" placeholder="搜索名称、代码或关注理由" @input="searchChanged" /><span v-if="pageData">共 {{ pageData.total }} 条</span><button :disabled="listLoading" @click="loadList">刷新清单</button></div>
    <div v-if="selectedId!==null" ref="detailSection" class="detail-panel" tabindex="-1">
      <header class="section-header"><h3>关注详情 · 截至 {{ date }}</h3><button @click="closeDetail">收起详情</button></header>
      <p v-if="detailLoading" class="muted">正在核对这条关注…</p><p v-if="detailError" class="error" role="alert">{{ detailError }}</p>
      <template v-if="detail&&!detailLoading">
        <header class="detail-title"><button class="stock-link" @click="$emit('open',detail.observation.code,detail.observation.name)">{{ detail.observation.name }} {{ detail.observation.code }}</button><span>{{ detail.observation.verdict }}</span><small>{{ detail.observation.observation_date }} → {{ detail.observation.deadline }}</small></header>
        <p><b>原始理由</b> {{ detail.observation.reason }}</p><p><b>原始条件</b> {{ detail.observation.criterion }}</p>
        <div class="facts"><span>关注日原始收盘 {{ detail.observation.base_close??'—' }}</span><span>所选日原始收盘 {{ detail.observation.close??'—' }}</span><span>复权区间变化 {{ detail.observation.adjusted_price_change==null?'—':detail.observation.adjusted_price_change+'%' }}</span><span>原始收盘变化 {{ detail.observation.price_change==null?'—':detail.observation.price_change+'%' }}</span></div>
        <small>实际录入 {{ time(detail.observation.created_at) }}<template v-if="detail.observation.verified_on"> · 验证所属 {{ detail.observation.verified_on }} · 实际保存 {{ time(detail.observation.verified_at!) }}</template></small>
        <p v-if="detail.observation.explanation"><b>人工验证依据</b> {{ detail.observation.explanation }}</p>
        <button @click="openVerification">记录 {{ date }} 的验证</button>
        <form v-if="verificationOpen" class="verify-form" @submit.prevent="verify"><fieldset :disabled="verifying"><select v-model="verdict"><option>符合预期</option><option>不符合预期</option><option>继续观察</option></select><textarea v-model="explanation" maxlength="2000" rows="3" required placeholder="对照原始条件，说明哪些事实支持你的判断。"></textarea><div class="actions"><button class="primary" :disabled="verifying">{{ verifying?'保存中…':'保存人工验证' }}</button><button type="button" @click="verificationOpen=false">收起</button></div></fieldset></form>
        <ReviewObservationAssistant :key="detail.observation.id" :date="date" :observation="detail.observation" :entry="detail.entry" :ai="detail.ai" @changed="$emit('saved')" @feedback-changed="$emit('feedbackChanged')" />
      </template>
    </div>
    <p v-if="listLoading" class="empty">正在读取关注清单…</p>
    <template v-else-if="pageData">
      <article v-for="row in pageData.items" :key="row.id" class="compact-row" :class="{selected:selectedId===row.id}">
        <div class="row-main"><button class="stock-link" @click="focus(row.id)">{{ row.name }} <small>{{ row.code }}</small></button><span class="verdict">{{ row.verdict }}</span><p class="reason" :title="row.reason">{{ row.reason }}</p><small>关注 {{ row.observation_date }} · 验证 {{ row.deadline }}<template v-if="row.last_audit"> · 上次 AI 审阅 {{ row.last_audit.date }}</template></small></div>
        <div class="row-state"><span :class="{warning:row.evaluation.status==='not_met'||row.evaluation.status==='unknown'}">{{ row.evaluation.label }}</span><p>{{ nextAction(row) }}</p><small v-if="row.evaluation.first_violation">首次反例 {{ row.evaluation.first_violation }}</small><small v-else-if="row.last_audit?.changes.length">上次审阅后有新资料</small></div>
        <button @click="focus(row.id)">{{ selectedId===row.id?'正在查看':'查看 / 处理' }}</button>
      </article>
      <p v-if="!pageData.items.length" class="empty">没有匹配关注。可调整筛选，或新增一条带理由和验证期限的记录。</p>
      <div v-if="pageData.pages>1" class="pagination"><button :disabled="pageData.page<=1" @click="go(pageData.page-1)">上一页</button><span>{{ pageData.page }} / {{ pageData.pages }} · 每页 {{ pageData.page_size }} 条</span><button :disabled="pageData.page>=pageData.pages" @click="go(pageData.page+1)">下一页</button></div>
    </template>
  </section>
</template>
<script setup lang="ts">
import { computed, nextTick, onUnmounted, reactive, ref, watch } from 'vue'
import { createReviewObservation, fetchReviewDeadlines, fetchReviewObservation, fetchReviewObservations, verifyReviewObservation } from '../../api/client'
import type { ReviewConditionSpec, ReviewObservationDetail, ReviewObservationPage, ReviewObservationSummary } from '../../api/client'
import { createLatestLoader } from '../../utils/latestLoader'
import ReviewStockSearch from './ReviewStockSearch.vue'
import ReviewObservationAssistant from './ReviewObservationAssistant.vue'
const props=defineProps<{date:string;revision:number}>()
const emit=defineEmits<{saved:[];open:[code:string,name:string];feedbackChanged:[]}>()
const showForm=ref(false),saving=ref(false),notice=ref(''),error=ref(''),preset=ref('custom'),operator=ref<'ge'|'le'>('ge'),threshold=ref('0'),ruleConfirmed=ref(false)
const form=reactive({code:'',reason:'',criterion:'',deadline:''})
const deadlineOptions=ref<{days:number;date:string}[]>([]),calendarLoading=ref(false),deadlineError=ref(''),duration=ref<number|string>('manual')
const pageData=ref<ReviewObservationPage|null>(null),listLoading=ref(false),status=ref('pending'),search=ref(''),page=ref(1)
const selectedId=ref<number|null>(null),detail=ref<ReviewObservationDetail|null>(null),detailLoading=ref(false),detailError=ref(''),detailSection=ref<HTMLElement|null>(null)
const verificationOpen=ref(false),verifying=ref(false),verdict=ref('继续观察'),explanation=ref('')
let disposed=false,generation=0,detailGeneration=0,searchTimer:ReturnType<typeof setTimeout>|undefined
const listLoader=createLatestLoader<ReviewObservationPage>({resolve:value=>{pageData.value=value;page.value=value.page},reject:()=>{pageData.value=null;error.value='关注清单读取失败，请重试。'},pending:value=>listLoading.value=value})
const detailLoader=createLatestLoader<ReviewObservationDetail>({resolve:value=>detail.value=value,reject:(e:any)=>{detail.value=null;detailError.value=e?.response?.data?.detail||'关注详情读取失败，请重试。'},pending:value=>detailLoading.value=value})
const calendarLoader=createLatestLoader<{date:string;options:{days:number;date:string}[]}>({resolve:value=>{deadlineOptions.value=value.options;if(!form.deadline){duration.value=5;form.deadline=value.options.find(row=>row.days===5)?.date||''}},reject:()=>{deadlineOptions.value=[];duration.value='manual';deadlineError.value='交易日期暂未确认，请手动选择验证日期，或稍后更新日历。'},pending:value=>calendarLoading.value=value})
const templateText=computed(()=>(preset.value==='hold_change'?'关注后至验证期限内，每个交易日收盘':'验证期限日（休市时取此前最后一个交易日）收盘')+'较关注日的复权区间价格变化'+(operator.value==='ge'?'不低于 ':'不高于 ')+threshold.value+'%。')
function message(e:any,fallback:string){return typeof e?.response?.data?.detail==='string'?e.response.data.detail:fallback}
function time(value:string|null){return value?new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}).format(new Date(value)):'未知'}
function loadList(){error.value='';if(searchTimer)clearTimeout(searchTimer);return listLoader.load(signal=>fetchReviewObservations(props.date,status.value,search.value.trim(),page.value,signal))}
function loadDetail(){if(selectedId.value===null)return;detailError.value='';const id=selectedId.value;return detailLoader.load(signal=>fetchReviewObservation(id,props.date,signal))}
function loadDeadlines(){deadlineError.value='';return calendarLoader.load(signal=>fetchReviewDeadlines(props.date,signal))}
function toggleForm(){showForm.value=!showForm.value;if(showForm.value&&!deadlineOptions.value.length)loadDeadlines()}
function selectDuration(event:Event){const value=(event.target as HTMLSelectElement).value;duration.value=value==='manual'?'manual':Number(value);if(value!=='manual')form.deadline=deadlineOptions.value.find(row=>row.days===Number(value))?.date||''}
watch([preset,operator,threshold,()=>form.deadline],()=>{ruleConfirmed.value=false;if(preset.value!=='custom')form.criterion=templateText.value})
function changeFilter(){page.value=1;loadList()}
function searchChanged(){if(searchTimer)clearTimeout(searchTimer);listLoader.cancel();pageData.value=null;page.value=1;searchTimer=setTimeout(loadList,250)}
function go(value:number){page.value=value;loadList()}
async function focus(id:number){detailGeneration++;selectedId.value=id;detail.value=null;verificationOpen.value=false;await nextTick();detailSection.value?.scrollIntoView({behavior:'smooth',block:'start'});detailSection.value?.focus({preventScroll:true});await loadDetail()}
function closeDetail(){detailGeneration++;selectedId.value=null;detail.value=null;verificationOpen.value=false;detailLoader.cancel()}
function nextAction(row:ReviewObservationSummary){
  if(row.verdict==='符合预期'&&row.evaluation.status==='not_met')return '核对人工结论与价格反例'
  if(['待验证','继续观察'].includes(row.verdict)&&row.deadline<=props.date)return '记录到期验证或继续观察的依据'
  if(row.evaluation.status==='not_configured')return '可补充价格规则，或保留文字验证'
  if(row.evaluation.status==='unknown')return '核对缺失资料，暂不作通过判断'
  if(row.last_audit?.stale)return '查看上次意见与此后变化'
  return ['待验证','继续观察'].includes(row.verdict)?'继续按原条件观察':'查看原判断与验证记录'
}
async function create(){
  if(saving.value)return
  if(!/^\d{6}$/.test(form.code)){error.value='请搜索并选择股票，或输入完整六位股票代码。';return}
  const current=generation,date=props.date
  const condition:ReviewConditionSpec|undefined=ruleConfirmed.value&&preset.value!=='custom'?{kind:preset.value as ReviewConditionSpec['kind'],operator:operator.value,threshold_pct:String(threshold.value),price_basis:'adjusted',note:'录入时人工确认：'+templateText.value}:undefined
  const body={...form,observation_date:date,condition}
  saving.value=true;notice.value='';error.value=''
  try{const result=await createReviewObservation(body);if(disposed||generation!==current)return;showForm.value=false;form.code='';form.reason='';form.criterion=preset.value==='custom'?'':templateText.value;ruleConfirmed.value=false;notice.value=condition?'关注与已确认规则已一起保存。':'关注已保存。';selectedId.value=result.id;detail.value=null;verificationOpen.value=false;emit('saved');await nextTick();detailSection.value?.scrollIntoView({behavior:'smooth',block:'start'})}
  catch(e:any){if(!disposed&&generation===current)error.value=message(e,'保存结果尚未确认，请刷新清单核对后再提交。')}
  finally{if(generation===current)saving.value=false}
}
function openVerification(){if(!detail.value)return;verdict.value=detail.value.observation.verdict==='待验证'?'继续观察':detail.value.observation.verdict;explanation.value=detail.value.observation.explanation;verificationOpen.value=true}
async function verify(){
  if(!detail.value||verifying.value)return
  const current=generation,focused=detailGeneration,id=detail.value.observation.id,date=props.date
  const submittedVerdict=verdict.value,submittedExplanation=explanation.value
  verifying.value=true;error.value='';notice.value=''
  try{await verifyReviewObservation(id,date,submittedVerdict,submittedExplanation);if(disposed||generation!==current)return;notice.value='人工验证已保存，原始理由继续保留。';if(detailGeneration===focused)verificationOpen.value=false;emit('saved')}
  catch(e:any){if(!disposed&&generation===current)error.value=message(e,'验证结果尚未确认，请刷新核对。')}
  finally{if(generation===current)verifying.value=false}
}
watch(()=>[props.date,props.revision],(value,old)=>{if(!old||value[0]!==old[0]){generation++;detailGeneration++;saving.value=false;verifying.value=false;closeDetail();showForm.value=false;form.code='';form.reason='';form.criterion=preset.value==='custom'?'':templateText.value;form.deadline='';deadlineOptions.value=[];calendarLoader.cancel();duration.value='manual';page.value=1;notice.value='';error.value=''}loadList();if(selectedId.value!==null)loadDetail()},{immediate:true})
function prefillStock(code:string){form.code=code;showForm.value=true;if(!deadlineOptions.value.length)loadDeadlines()}
onUnmounted(()=>{disposed=true;generation++;detailGeneration++;listLoader.dispose();detailLoader.dispose();calendarLoader.dispose();if(searchTimer)clearTimeout(searchTimer)})
defineExpose({focus,prefillStock})
</script>
<style scoped>
.panel{background:#111827;border:1px solid #29384e;border-radius:12px;padding:22px;scroll-margin-top:20px;font-size:13px}.section-header,.actions,.deadline-row,.filters,.facts,.detail-title,.pagination{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.section-header{justify-content:space-between}h2{margin:0 0 7px;font-size:18px;color:#f3f4f6}h3{font-size:15px;color:#e5e7eb;margin:0}small,.muted,.facts{font-size:12px;color:#9ca3af;line-height:1.9}button,input,select,textarea{background:#111c2e;border:1px solid #374b65;border-radius:6px;color:#d1d5db;padding:8px 11px;font-size:12px}button{cursor:pointer}button:disabled{opacity:.4;cursor:default}button.primary{background:#24446a;border-color:#4c709b;color:#eff6ff}.stock-link{color:#93c5fd;border:0;background:none;padding:0;font-size:14px;font-weight:600;text-align:left}.stock-link small{margin-left:8px}textarea{width:100%;box-sizing:border-box;display:block;resize:vertical;line-height:1.9;margin:8px 0 12px}label{font-size:12px;color:#aebed3;line-height:1.9}fieldset{border:0;padding:0;min-width:0}.create-form{background:#0d1727;padding:20px;border-radius:9px;margin:18px 0;border:1px solid #2a405d}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.form-grid label>select{display:block;width:100%;margin-top:5px;padding:10px}.deadline-row{margin:18px 0}.deadline-row>span{color:#94a3b8;font-size:12px}.deadline-row label{display:flex;align-items:center;gap:8px}.price-template{display:flex;align-items:center;gap:14px;flex-wrap:wrap;background:#142238;padding:14px;border-radius:7px;margin:12px 0}.price-template input{max-width:100px}.price-template p{width:100%;margin:0;color:#bfdbfe;line-height:1.8}.confirmation{display:flex;align-items:flex-start;gap:8px;margin:12px 0}.confirmation input{margin-top:6px}.actions{margin-top:14px}.filters{padding:16px 0;margin-top:12px;border-block:1px solid #26364c}.filters>input{flex:1;min-width:180px}.filters>span{color:#94a3b8;font-size:12px}.compact-row{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(180px,1fr) auto;align-items:center;gap:20px;padding:18px 10px;border-bottom:1px solid #26364c}.compact-row.selected{background:#142238}.row-main{min-width:0}.verdict{display:inline-block;margin-left:12px;color:#a5b4c8;font-size:11px;background:#1d2a3e;padding:3px 6px;border-radius:4px}.reason{overflow:hidden;white-space:nowrap;text-overflow:ellipsis;color:#d1d5db;line-height:1.8;margin:9px 0}.row-state>span{color:#cbd5e1;font-size:12px}.row-state p{color:#94a3b8;font-size:12px;line-height:1.8;margin:7px 0}.warning,.notice{color:#fcd34d!important}.error{color:#fca5a5}.empty{text-align:center;padding:28px;color:#94a3b8}.detail-panel{background:#0c1626;border:1px solid #3d587b;border-radius:10px;padding:20px;margin:18px 0;scroll-margin-top:20px;outline:none}.detail-panel>p{color:#cbd5e1;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.9}.detail-title{margin:20px 0 14px}.detail-title>span{font-size:12px;color:#bfdbfe}.facts{margin:14px 0}.verify-form{margin-top:14px;background:#111f33;padding:15px;border-radius:8px}.pagination{justify-content:center;color:#9ca3af;font-size:12px;margin-top:18px}@media(max-width:750px){.panel{padding:16px}.form-grid{grid-template-columns:1fr}.compact-row{grid-template-columns:1fr auto;gap:10px}.row-main{grid-column:1/-1}.row-state{min-width:0}.detail-panel{padding:15px}.deadline-row{align-items:flex-start;flex-direction:column}.deadline-row label{flex-wrap:wrap}.create-form{padding:14px}}
</style>
