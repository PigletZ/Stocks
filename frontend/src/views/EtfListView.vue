<template>
  <div class="workspace">
    <header><div><span class="eyebrow">跨方向复盘 / 场内基金</span><h1>ETF 观察台</h1><p>{{ fundView?'分别核对成交、份额和披露证据，买方身份独立判断。':'先看方向是否持续，再比较同类基金的活跃程度。' }}</p></div><div class="controls"><input aria-label="观察日期" type="date" v-model="date" :max="today" /><select v-if="!fundView" aria-label="成交额门槛" v-model.number="minAmount"><option :value="10000000">成交额 ≥ 1000 万</option><option :value="50000000">成交额 ≥ 5000 万</option><option :value="0">不限成交额</option></select><button v-if="!fundView" @click="load" :disabled="loading">{{ loading ? '整理数据中…' : '更新观察' }}</button></div></header><nav class="view-nav"><button :class="{active:fundView}" @click="changeView('funds')">宽基资金观察</button><button :class="{active:!fundView}" @click="changeView('performance')">行情与方向</button></nav><EtfFundsPanel v-if="fundView" :date="date" />
    <p v-if="!fundView && error" class="error" role="alert">{{ error }}</p>
    <p v-if="!fundView && loading" class="notice">正在读取交易日历及多周期行情，首次加载可能较慢。</p>
    <template v-if="!fundView && data && !loading">
      <div class="status">实际数据 {{ data.effective_date }}<span v-if="data.effective_date !== data.target_date"> · 所选 {{ data.target_date }} 暂未取得行情，显示最近可用数据</span> · {{ data.quoted_count }} 只有效报价 / {{ data.items.length }} 只符合门槛（成交额 ≥ {{ amount(data.min_amount) }}）</div>
      <p v-if="data.cache_fallbacks?.length" class="notice" role="status">数据接口暂不可用或返回不完整，以下资料使用已有缓存，行情日期见上方：<span v-for="(entry, index) in data.cache_fallbacks" :key="entry.resource">{{ index ? '；' : '' }}{{ entry.resource }}（缓存于 {{ cacheTime(entry.fetched_at) }}）</span>。</p>
      <div class="guide"><p>方向强弱使用同类 ETF 的价格涨幅中位数，避免榜单被同一方向的多只基金占满。</p><small>分类由名称和基准关键词推断，同类不一定跟踪同一指数。成交额仅表示活跃程度，不是资金净流入。2/5/10/20 日按对应日期复权因子比较；原始收盘变化可悬停查看。不含溢价、费率和跟踪误差，不等于账户实际收益。</small></div>
      <p v-if="data.missing_windows.length" class="notice">{{ data.missing_windows.join('、') }} 日基准数据缺失，相关指标留空。</p>
      <p v-if="Object.values(data.factor_coverage).some(value=>value.valid<value.total)" class="notice">部分复权因子或基准报价缺失，相关区间留空，不参与方向中位数及短长状态判断。</p><p class="note">复权可比样本：<span v-for="(value,key) in data.factor_coverage" :key="key">{{ key }}日 {{ value.valid }}/{{ value.total }}　</span></p>
      <section class="panel"><div class="section-header"><div><h2>方向强弱</h2><small>按 5 日价格涨幅中位数排序 · 正涨样本 / 有效样本</small></div><div><button :class="{active: directionMode === 'up'}" @click="directionMode='up'">领涨</button><button :class="{active: directionMode === 'down'}" @click="directionMode='down'">领跌</button></div></div>
        <div class="directions"><button v-for="group in directions" :key="group.category" class="direction" :class="{chosen: category === group.category}" @click="category = category === group.category ? '' : group.category"><span>{{ group.category }}</span><strong :class="tone(group.median_5)">{{ pct(group.median_5) }}</strong><small>20日 {{ pct(group.median_20) }} · {{ group.positive_5 }}/{{ group.samples_5 }} 上涨</small><small>{{ group.count }} 只 · 点击查看同类</small></button></div><p v-if="!directions.length" class="empty">暂无符合条件的方向</p>
      </section>
      <section class="panel">
        <div class="tabs"><button :class="{active: mode === 'all'}" @click="mode='all'">全部 ETF</button><button :class="{active: mode === 'watch'}" @click="mode='watch'">我的观察 {{ watched.length }}</button><button :class="{active: mode === 'compare'}" @click="mode='compare'">对比 {{ compared.length }}/3</button></div>
        <div class="filters"><input aria-label="搜索 ETF" placeholder="搜索代码、名称或跟踪基准" v-model="search" /><select v-model="category"><option value="">全部方向</option><option v-for="c in categories" :key="c" :value="c">{{ c }}</option></select><select v-model="state"><option value="">全部短长状态</option><option v-for="s in states" :key="s">{{ s }}</option></select><select v-model="sort"><option value="amount">成交额优先</option><option value="gain_2">2日涨幅优先</option><option value="gain_5">5日涨幅优先</option><option value="gain_20">20日涨幅优先</option></select><button @click="search=''; category=''; state=''">清除筛选</button></div>
        <p class="note">短长同强：5日和20日均上涨；短强长弱：2日上涨、20日非正；短弱长强：2日非正、20日上涨。是历史表现描述，不是买卖信号。</p>
        <p v-if="storageError" class="notice">{{ storageError }}</p>
        <div v-if="mode === 'compare'" class="compare-grid"><article v-for="fund in compareRows" :key="fund.code"><h3>{{ fund.name }}</h3><small>{{ fund.code }} · {{ fund.category }}</small><p>5日 {{ pct(fund.gain_5) }} / 20日 {{ pct(fund.gain_20) }}</p><p>成交额 {{ amount(fund.amount) }}</p><p>管理人：{{ fund.management || '—' }}</p><p>跟踪基准：{{ fund.benchmark || '—' }}</p><small>先核对跟踪指数是否相同；仅凭涨幅和成交额不能判断哪只基金更优。</small><button @click="toggleCompare(fund.code)">移出对比</button></article></div>
        <p v-if="mode === 'compare' && !compareRows.length" class="empty">从 ETF 列表勾选最多 3 只基金进行对比。</p>
        <p v-if="mode === 'watch'" class="note">观察列表仅保存在当前浏览器；不满足当前日期或成交额门槛的基金不会出现在下表。可降低门槛查看。</p>
        <div v-if="mode !== 'compare'" class="table-wrap"><table><thead><tr><th>观察 / 对比</th><th>ETF / 方向</th><th>当日</th><th>2日</th><th>5日</th><th>10日</th><th>20日</th><th>当日成交额</th><th>短长状态</th></tr></thead><tbody><tr v-for="fund in visibleRows" :key="fund.code"><td><button :aria-label="'观察'+fund.name" @click="toggleWatch(fund.code)">{{ watched.includes(fund.code) ? '★' : '☆' }}</button><input type="checkbox" :aria-label="'对比'+fund.name" :checked="compared.includes(fund.code)" :disabled="compared.length>=3 && !compared.includes(fund.code)" @change="toggleCompare(fund.code)" /></td><td><b>{{ fund.name }}</b><small>{{ fund.code }} · {{ fund.category }}</small></td><td :class="tone(fund.change_pct)">{{ pct(fund.change_pct) }}</td><td :title="'原始收盘变化 '+pct(fund.raw_gain_2)" :class="tone(fund.gain_2)">{{ pct(fund.gain_2) }}</td><td :title="'原始收盘变化 '+pct(fund.raw_gain_5)" :class="tone(fund.gain_5)">{{ pct(fund.gain_5) }}</td><td :title="'原始收盘变化 '+pct(fund.raw_gain_10)" :class="tone(fund.gain_10)">{{ pct(fund.gain_10) }}</td><td :title="'原始收盘变化 '+pct(fund.raw_gain_20)" :class="tone(fund.gain_20)">{{ pct(fund.gain_20) }}</td><td>{{ amount(fund.amount) }}</td><td>{{ fund.state }}</td></tr></tbody></table></div>
        <p v-if="mode !== 'compare' && !rows.length" class="empty">没有匹配的 ETF，请调整筛选条件。</p>
        <div v-if="mode !== 'compare'" class="pagination"><button @click="page--" :disabled="page<=1">上一页</button><span>{{ page }} / {{ pages }} · {{ rows.length }} 只</span><button @click="page++" :disabled="page>=pages">下一页</button></div>
        <small>区间基准：<span v-for="w in [2,5,10,20]" :key="w">{{ w }}日 {{ data.base_dates[String(w)] || '—' }}　</span></small>
      </section>
    </template>
  </div>
</template>
<script setup lang="ts">
import { computed,defineAsyncComponent,onMounted,onUnmounted,ref,watch } from 'vue'
import {useRoute,useRouter} from 'vue-router'
import { fetchEtfDashboard } from '../api/client'
import type { EtfDashboard } from '../api/client'
const today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date())
const route=useRoute(),router=useRouter(),fundView=computed(()=>route.query.view!=='performance')
const EtfFundsPanel=defineAsyncComponent(()=>import('../components/EtfFundsPanel.vue'))
const initialDate=typeof route.query.date==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(route.query.date)?route.query.date:today
const date=ref(initialDate), minAmount=ref(10000000), data=ref<EtfDashboard|null>(null), loading=ref(false), error=ref('')
const search=ref(''),category=ref(''),state=ref(''),sort=ref<'amount'|'gain_2'|'gain_5'|'gain_20'>('amount'),mode=ref('all'),directionMode=ref('up'),page=ref(1)
const states=['短长同强','短强长弱','短弱长强','其他/分化','数据不足']
const watched=ref<string[]>([]),compared=ref<string[]>([]),storageError=ref('')
let controller:AbortController|null=null
const categories=computed(()=>[...new Set(data.value?.items.map(r=>r.category)||[])].sort())
const directions=computed(()=>[...(data.value?.directions || [])].filter(g=>g.median_5 != null && g.category!=='其他' && (directionMode.value==='up'?g.median_5>0:g.median_5<0)).sort((a,b)=>directionMode.value==='up'?(b.median_5! - a.median_5!):(a.median_5! - b.median_5!)).slice(0,8))
const rows=computed(()=> (data.value?.items || []).filter(r=>(mode.value!=='watch'||watched.value.includes(r.code)) && (!category.value || category.value===r.category) && (!state.value || state.value===r.state) && `${r.code} ${r.name} ${r.benchmark}`.toLowerCase().includes(search.value.toLowerCase().trim())).sort((a,b)=>{const av=a[sort.value],bv=b[sort.value];return av==null?bv==null?0:1:bv==null?-1:bv-av}))
const pages=computed(()=>Math.max(1,Math.ceil(rows.value.length/30)))
const visibleRows=computed(()=>rows.value.slice((page.value-1)*30,page.value*30))
const compareRows=computed(()=>data.value?.items.filter(r=>compared.value.includes(r.code)) || [])
watch([search,category,state,sort,mode,watched],()=>page.value=1)
async function load(){controller?.abort();const request=new AbortController();controller=request;loading.value=true;error.value='';try{const result=await fetchEtfDashboard(date.value,minAmount.value,request.signal);if(request.signal.aborted)return;data.value=result;page.value=1;if(!result.items.some(r=>r.category===category.value))category.value=''}catch(e:any){if(!request.signal.aborted){data.value=null;error.value=e?.response?.data?.detail || 'ETF 数据加载失败，请稍后重试。'}}finally{if(controller===request)loading.value=false}}
function cacheTime(value:string){return new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}).format(new Date(value))}
function toggleWatch(code:string){watched.value=watched.value.includes(code)?watched.value.filter(c=>c!==code):[...watched.value,code];try{localStorage.setItem('stocks_etf_observations',JSON.stringify(watched.value));storageError.value=''}catch{storageError.value='浏览器无法保存观察列表，本次选择仅在当前页面有效。'}}
function toggleCompare(code:string){compared.value=compared.value.includes(code)?compared.value.filter(c=>c!==code):compared.value.length<3?[...compared.value,code]:compared.value}
function pct(v:number|null){return v==null?'—':`${v>0?'+':''}${v.toFixed(2)}%`}
function tone(v:number|null){return v==null||v===0?'':v>0?'up':'down'}
function amount(v:number){return v>=1e8?`${(v/1e8).toFixed(2)} 亿`:`${(v/1e4).toFixed(0)} 万`}
onMounted(()=>{try{const saved=JSON.parse(localStorage.getItem('stocks_etf_observations')||'[]');if(Array.isArray(saved))watched.value=saved.filter((v:unknown):v is string=>typeof v==='string'&&/^\d{6}$/.test(v))}catch{storageError.value='观察列表读取失败，可重新添加。'}if(!fundView.value)load()})
function changeView(view:string){router.replace({query:{...route.query,view,date:date.value}})}
watch(fundView,value=>{controller?.abort();loading.value=false;error.value='';if(!value)load()})
watch(date,value=>{if(!value){date.value=today;return}if(route.query.date!==value)router.replace({query:{...route.query,date:value,fund_batch:undefined}})})
watch(()=>route.query.date,value=>{if(typeof value==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(value)&&value!==date.value)date.value=value})
onUnmounted(()=>controller?.abort())
</script>
<style scoped>
.view-nav{display:flex;gap:10px;margin-top:22px;flex-wrap:wrap}.workspace{padding:28px;max-width:1500px;margin:auto;font-variant-numeric:tabular-nums}header,.controls,.section-header,.filters,.tabs,.pagination{display:flex;align-items:center;gap:12px;flex-wrap:wrap}header,.section-header{justify-content:space-between}h1{font-size:28px;margin:8px 0;color:#fff}h2{font-size:17px;margin:0 0 8px}h3{font-size:15px}.eyebrow{color:#60a5fa;font-size:12px;letter-spacing:2px}p{font-size:13px;line-height:1.8;color:#d1d5db}small,.status,.note{color:#9ca3af;font-size:12px;line-height:1.8}button,input,select{border:1px solid #374151;border-radius:6px;background:#111827;color:#d1d5db;padding:7px 10px}button{cursor:pointer}button:disabled{opacity:.4;cursor:default}.active,.chosen{border-color:#60a5fa!important;background:#172554!important;color:#fff}.status{margin:20px 0;padding:12px 0;border-block:1px solid #253045}.guide{border-left:3px solid #60a5fa;background:linear-gradient(110deg,#152239,#111827);padding:12px 18px;border-radius:8px}.guide p{margin:0 0 5px}.panel{background:#111827;border:1px solid #253045;border-radius:12px;padding:20px;margin-top:22px}.directions{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin-top:18px}.direction{display:flex;flex-direction:column;align-items:flex-start;gap:7px;padding:16px;background:#0b1220}.direction strong{font-size:24px}.filters{margin:18px 0}.filters input{flex:1;min-width:160px}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:13px;white-space:nowrap}th{font-weight:400;color:#9ca3af;background:#0b1220}td,th{text-align:left;padding:12px;border-bottom:1px solid #253045}td small{display:block}td input{margin-left:10px}.up{color:#ef4444}.down{color:#22c55e}.pagination{justify-content:center;margin:18px 0;font-size:12px}.compare-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}.compare-grid article{background:#0b1220;border-radius:8px;padding:18px}.compare-grid p{word-break:break-word}.compare-grid button{display:block;margin-top:14px}.error{color:#fca5a5;background:#450a0a;padding:12px}.notice{color:#fbbf24}.empty{text-align:center;padding:24px;color:#9ca3af}@media(max-width:700px){.view-nav{display:flex;gap:10px;margin-top:22px;flex-wrap:wrap}.workspace{padding:16px}.panel{padding:14px}.directions{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>
