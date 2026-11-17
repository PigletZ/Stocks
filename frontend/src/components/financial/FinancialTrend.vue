<template><section class="panel"><header><div><h2>同期经营趋势</h2><p>只比较相同季末的累计报告，截止 {{ period }}；缺失值留空。</p></div><select v-model="code"><option v-for="s in stocks" :key="s.code" :value="s.code">{{ s.name }}</option></select><select v-model="mode"><option value="money">收入、利润与现金流</option><option value="margin">毛利率与净利率</option></select></header><p v-if="periods.length<2">同期数据不足两期，暂无法判断趋势。</p><div ref="container" class="chart"></div></section></template>
<script setup lang="ts">
import { computed,ref,watch,onMounted,onUnmounted } from 'vue'
import * as echarts from 'echarts'
import type { FinStockCompare,FinMetrics } from '../../api/client'
const props=defineProps<{stocks:FinStockCompare[];period:string}>()
const code=ref(props.stocks[0]?.code || ''), mode=ref('money')
const stock=computed(()=>props.stocks.find(s=>s.code===code.value))
const periods=computed(()=>stock.value?.periods.filter(p=>p<=props.period && p.slice(5)===props.period.slice(5)).sort() || [])
const container=ref<HTMLDivElement|null>(null)
let chart:echarts.ECharts|null=null, observer:ResizeObserver|null=null
function render(){
 if(!chart)return
 const keys:{key:keyof FinMetrics;name:string}[]=mode.value==='money'?[{key:'revenue',name:'营业总收入'},{key:'net_profit',name:'归母净利润'},{key:'ncf',name:'经营现金流'}]:[{key:'gross_margin',name:'毛利率'},{key:'net_margin',name:'净利率'}]
 chart.setOption({animation:false,tooltip:{trigger:'axis'},legend:{bottom:0,textStyle:{color:'#9ca3af'}},grid:{left:65,right:20,top:35,bottom:55},xAxis:{type:'category',data:periods.value,axisLabel:{color:'#9ca3af'}},yAxis:{type:'value',name:mode.value==='money'?'亿元':'%',nameTextStyle:{color:'#9ca3af'},axisLabel:{color:'#9ca3af'},splitLine:{lineStyle:{color:'#253045'}}},series:keys.map((k,i)=>({name:k.name,type:'line',connectNulls:false,itemStyle:{color:['#60a5fa','#fbbf24','#34d399'][i]},data:periods.value.map(p=>{const v=stock.value?.metrics[p]?.[k.key];return typeof v==='number'?v*(mode.value==='money'?1e-8:100):null})}))},true)
}
watch(()=>props.stocks,()=>{if(!props.stocks.some(s=>s.code===code.value))code.value=props.stocks[0]?.code || ''})
watch([stock,periods,mode],render)
onMounted(()=>{if(container.value){chart=echarts.init(container.value);observer=new ResizeObserver(()=>chart?.resize());observer.observe(container.value);render()}})
onUnmounted(()=>{observer?.disconnect();chart?.dispose()})
</script>
<style scoped>.panel{background:#111827;border:1px solid #253045;padding:22px;border-radius:12px}header{display:flex;gap:12px;align-items:center;flex-wrap:wrap}h2{font-size:16px;color:#fff;margin:0}p{color:#9ca3af;font-size:12px}select{background:#1f2937;color:#e5e7eb;padding:6px;border:1px solid #374151;border-radius:6px}.chart{height:290px;width:100%}</style>
