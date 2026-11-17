<template>
  <section class="panel">
    <div class="section-header"><div><h2>我的关注验证</h2><small>保留原始理由，分别记录后续价格表现和你的判断。</small></div><button @click="showForm = !showForm">{{ showForm ? '收起录入' : '新增关注' }}</button></div>
    <p class="notice">关注和验证均保留实际录入时间；历史补录不代表当时已作出判断。当前显示截至 {{ date }} 的最近 500 条记录。价格变化未复权，不等于投资收益。</p>
    <form v-if="showForm" class="form" @submit.prevent="create">
      <input aria-label="股票代码" v-model="form.code" placeholder="A股代码，如 600519" pattern="\d{6}" maxlength="6" required />
      <label>关注日期 {{ date }}</label><label>验证期限 <input type="date" v-model="form.deadline" :min="date" required /></label>
      <textarea v-model="form.reason" maxlength="2000" placeholder="为什么关注？记录当时看到的事实和判断依据。" required></textarea>
      <textarea v-model="form.criterion" maxlength="2000" placeholder="具体观察什么？怎样才算符合原来的预期？" required></textarea>
      <button :disabled="saving">{{ saving ? '保存中…' : '保存原始关注' }}</button>
    </form>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div class="filters"><select v-model="filter"><option value="all">全部记录</option><option value="pending">待验证 / 继续观察</option><option value="due">已到验证期限</option></select><span>{{ filtered.length }} 条</span></div>
    <p v-if="!filtered.length" class="empty">暂无记录。可从下方强势股明细点击“关注”，从今天开始积累判断。</p>
    <article v-for="row in filtered" :key="row.id" class="observation">
      <header><button class="link" @click="$emit('open',row.code,row.name)">{{ row.name }} {{ row.code }}</button><span>{{ row.observation_date }} → {{ row.deadline }}</span><b>{{ row.verdict }}</b></header>
      <p><strong>原始理由</strong> {{ row.reason }}</p><p><strong>验证条件</strong> {{ row.criterion }}</p>
      <div class="facts"><span>关注日收盘 {{ row.base_close ?? '—' }}</span><span>所选日收盘 {{ row.close ?? '—' }}</span><span>价格变化 {{ row.price_change == null ? '—' : row.price_change + '%' }}</span></div>
      <small>实际录入 {{ localTime(row.created_at) }}<template v-if="row.verified_on"> · 验证所属日 {{ row.verified_on }} · 实际保存 {{ localTime(row.verified_at) }}</template></small>
      <p v-if="row.explanation"><strong>验证依据</strong> {{ row.explanation }}</p>
      <button @click="edit(row)">记录 {{ date }} 的验证</button>
      <form v-if="editing === row.id" class="form" @submit.prevent="verify(row.id)"><select v-model="verdict"><option>符合预期</option><option>不符合预期</option><option>继续观察</option></select><textarea v-model="explanation" maxlength="2000" required placeholder="对照原始条件，说明哪些事实支持你的结论。"></textarea><button :disabled="saving">保存验证</button><button type="button" @click="editing=null">取消</button></form>
    </article>
  </section>
</template>
<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { createReviewObservation, verifyReviewObservation } from '../../api/client'
import type { ReviewObservation } from '../../api/client'
const props=defineProps<{date:string;rows:ReviewObservation[];prefill?:string}>()
const emit=defineEmits<{saved:[];open:[code:string,name:string]}>()
const showForm=ref(false),saving=ref(false),error=ref(''),filter=ref('pending'),editing=ref<number|null>(null),verdict=ref('继续观察'),explanation=ref('')
const form=reactive({code:'',reason:'',criterion:'',deadline:props.date})
watch(()=>props.prefill,code=>{if(code){form.code=code;showForm.value=true}})
watch(()=>props.date,date=>{form.deadline=date;editing.value=null})
const filtered=computed(()=>props.rows.filter(r=>filter.value==='all'||filter.value==='pending'?(filter.value==='all'||['待验证','继续观察'].includes(r.verdict)):(r.deadline<=props.date&&['待验证','继续观察'].includes(r.verdict))))
function localTime(value:string|null){return value?new Date(value).toLocaleString('zh-CN',{hour12:false}):'—'}
function edit(row:ReviewObservation){editing.value=row.id;verdict.value=row.verdict==='待验证'?'继续观察':row.verdict;explanation.value=row.explanation}
async function create(){saving.value=true;error.value='';try{await createReviewObservation({...form,observation_date:props.date});form.code='';form.reason='';form.criterion='';showForm.value=false;emit('saved')}catch(e:any){error.value=e?.response?.data?.detail||'保存失败'}finally{saving.value=false}}
async function verify(id:number){saving.value=true;error.value='';try{await verifyReviewObservation(id,props.date,verdict.value,explanation.value);editing.value=null;emit('saved')}catch(e:any){error.value=e?.response?.data?.detail||'保存失败'}finally{saving.value=false}}
</script>
<style scoped>
.panel{background:#111827;border:1px solid #253045;border-radius:12px;padding:22px}.section-header,header,.facts,.filters{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.section-header{justify-content:space-between}h2{margin:0 0 7px;font-size:17px;color:#fff}small,.facts,.filters,header span{font-size:12px;color:#9ca3af;line-height:1.8}p{font-size:13px;color:#d1d5db;line-height:1.9;white-space:pre-wrap;overflow-wrap:anywhere}.notice{color:#9ca3af;font-size:12px}.observation{background:#0b1220;border-radius:8px;padding:18px;margin-top:14px}header b{color:#93c5fd;font-size:12px}.form{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}.form textarea{width:100%;min-height:70px}button,input,select,textarea{background:#111827;border:1px solid #374151;border-radius:6px;color:#d1d5db;padding:8px 12px}button{cursor:pointer}.link{color:#60a5fa;border:0;padding:0}label{font-size:12px;color:#9ca3af}.error{color:#fca5a5}.empty{color:#9ca3af;text-align:center;padding:24px}.filters{margin-top:16px}button:disabled{opacity:.5}
</style>
