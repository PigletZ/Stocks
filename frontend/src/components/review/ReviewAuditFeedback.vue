<template>
  <div class="feedback">
    <div v-if="current" class="saved-feedback"><strong>你的反馈 · {{ labels[current.rating] }}</strong><p v-if="current.comment">{{ current.comment }}</p><small>所属 {{ current.date }} · 实际保存 {{ time(current.created_at) }}</small><button :disabled="saving" @click="edit">修改反馈</button></div>
    <button v-else-if="!editing" @click="edit">反馈这条意见</button>
    <form v-if="editing" @submit.prevent="save"><fieldset :disabled="saving"><div class="rating-options"><label v-for="(label,key) in labels" :key="key"><input type="radio" v-model="rating" :value="key" required /> {{ label }}</label></div><textarea v-model="comment" maxlength="1000" rows="2" :required="rating!=='helpful'" :placeholder="rating==='helpful'?'可补充这条意见为什么有帮助':'请说明具体误解或缺少的证据，方便以后核对。'"></textarea><small>反馈所属 {{ date }}，记录实际保存时间；与 AI 原文、人工验证分别保留。</small><div class="actions"><button type="submit">{{ saving?'保存中…':'保存反馈' }}</button><button type="button" @click="editing=false">取消</button></div></fieldset></form>
    <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <details v-if="current&&current.revisions>1" @toggle="historyToggle"><summary>反馈记录（{{ current.revisions }} 次）</summary><p v-if="historyLoading">正在读取…</p><template v-else-if="history"><div v-for="row in history.items" :key="row.id" class="history-row"><b>{{ labels[row.rating] }}</b><p>{{ row.comment||'未填写补充说明' }}</p><small>所属 {{ row.date }} · 实际保存 {{ time(row.created_at) }}</small></div><div v-if="history.pages>1" class="actions"><button :disabled="history.page<=1" @click="loadHistory(history.page-1)">上一页</button><span>{{ history.page }}/{{ history.pages }}</span><button :disabled="history.page>=history.pages" @click="loadHistory(history.page+1)">下一页</button></div></template></details>
  </div>
</template>
<script setup lang="ts">
import { computed,onUnmounted,ref,watch } from 'vue'
import { fetchReviewAuditFeedbackHistory,saveReviewAuditFeedback } from '../../api/client'
import type { ReviewAudit,ReviewAuditFeedback,ReviewFeedbackHistory } from '../../api/client'
import { createLatestLoader } from '../../utils/latestLoader'
const props=defineProps<{observationId:number;auditId:number;date:string;section:keyof ReviewAudit['result'];itemIndex:number;value?:ReviewAuditFeedback}>()
const emit=defineEmits<{saved:[]}>()
const local=ref<ReviewAuditFeedback|null>(null),editing=ref(false),rating=ref<ReviewAuditFeedback['rating']>('helpful'),comment=ref(''),saving=ref(false),error=ref(''),notice=ref(''),history=ref<ReviewFeedbackHistory|null>(null),historyLoading=ref(false)
let generation=0,disposed=false
const labels={helpful:'有帮助',misunderstood:'理解有误',insufficient:'证据不足'}
const current=computed(()=>props.value && props.value.id>=(local.value?.id||0)?props.value:local.value)
const loader=createLatestLoader<ReviewFeedbackHistory>({resolve:value=>history.value=value,reject:()=>error.value='反馈记录读取失败，请重试。',pending:value=>historyLoading.value=value})
function time(value:string){return new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}).format(new Date(value))}
function edit(){rating.value=current.value?.rating||'helpful';comment.value=current.value?.comment||'';editing.value=true;notice.value='';error.value=''}
function loadHistory(page=1){return loader.load(signal=>fetchReviewAuditFeedbackHistory(props.observationId,props.auditId,props.date,props.section,props.itemIndex,page,signal))}
function historyToggle(event:Event){if((event.target as HTMLDetailsElement).open)loadHistory()}
async function save(){if(saving.value)return;const scope=generation;saving.value=true;notice.value='';error.value='';try{const result=await saveReviewAuditFeedback(props.observationId,props.auditId,{date:props.date,section:props.section,item_index:props.itemIndex,rating:rating.value,comment:comment.value});if(disposed||scope!==generation)return;local.value=result;editing.value=false;history.value=null;notice.value='反馈已保存，原意见和之前的反馈继续保留。';emit('saved')}catch(e:any){if(!disposed&&scope===generation)error.value=typeof e?.response?.data?.detail==='string'?e.response.data.detail:'反馈结果尚未确认，请刷新核对后再提交。'}finally{if(scope===generation)saving.value=false}}
watch(()=>[props.auditId,props.date,props.section,props.itemIndex],()=>{generation++;loader.cancel();local.value=null;history.value=null;editing.value=false;saving.value=false;error.value='';notice.value=''})
onUnmounted(()=>{disposed=true;generation++;loader.dispose()})
</script>
<style scoped>
.feedback{border-top:1px dashed #34445c;padding-top:10px;margin-top:12px;font-size:12px;color:#94a3b8}.feedback button{font-size:11px;padding:5px 9px;border:1px solid #3a506e;border-radius:5px;background:#16253b;color:#bfdbfe;cursor:pointer}.saved-feedback strong{display:block;color:#b3c8e3;font-size:12px}.saved-feedback p,.history-row p{color:#b8c5d6;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.8}.saved-feedback small,.history-row small{display:block;color:#8495ac;line-height:1.8;margin-bottom:8px}.rating-options,.actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.rating-options label{display:flex;align-items:center;gap:4px;color:#cbd5e1}fieldset{border:0;padding:0}.feedback textarea{width:100%;box-sizing:border-box;margin:10px 0;padding:8px;border:1px solid #3a506e;border-radius:5px;background:#0d1727;color:#cbd5e1;font-size:12px;line-height:1.8;resize:vertical}.feedback small{line-height:1.8}.actions{margin-top:10px}.feedback details{margin-top:10px}.feedback summary{cursor:pointer;color:#9fb7d6}.history-row{border-bottom:1px solid #2b3b51;padding:12px 0}.error{color:#fca5a5}.notice{color:#a5c7a4}.feedback button:disabled{opacity:.4}
</style>
