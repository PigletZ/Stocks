<template>
  <article class="card">
    <header><div><h2>{{ stock.name }} <small>{{ stock.code }}</small></h2><span>{{ stock.industry || '行业未知' }} · {{ stock.card.period }}</span></div></header>
    <div class="story"><p v-for="line in story" :key="line">{{ line }}</p></div>
    <div class="grid">
      <section><span>01 / 盈利表现</span><strong>{{ money(c.net_profit) }}</strong><p>归母净利润 · {{ c.net_profit_state || '缺少同期数据' }}</p><small>净利率 {{ pct(c.net_margin) }} · 毛利率 {{ pct(c.gross_margin) }}</small></section>
      <section><span>02 / 增长变化</span><strong>{{ pct(c.revenue_yoy,true) }}</strong><p>营业总收入同比 · 收入 {{ money(c.revenue) }}</p><small>净利润同比 {{ pct(c.net_profit_yoy,true) }}<template v-if="c.net_profit_yoy == null">（{{ c.net_profit_state || '不可比' }}）</template></small></section>
      <section><span>03 / 现金支撑</span><strong>{{ money(c.ncf) }}</strong><p>经营活动现金流净额</p><small>净现比 {{ ratio(c.ncf_ratio) }}<template v-if="c.net_profit == null || c.net_profit <= 0"> · 净利润非正或缺失时不计算</template></small></section>
      <section><span>04 / 负债状况</span><strong>{{ pct(c.debt_ratio) }}</strong><p>资产负债率 · 流动比率 {{ ratio(c.current_ratio) }}</p><small>需结合行业、债务结构判断，低负债不等于低风险</small></section>
    </div>
    <div class="tags"><span v-for="tag in stock.tags" :key="tag.label" :class="tag.type">{{ tag.type === 'risk' ? '关注' : '特征' }} · {{ tag.label }}</span></div>
    <footer>ROE 简单年化 {{ pct(c.roe_annualized) }} · 按期末净资产计算，非业绩预测</footer>
  </article>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import type { FinStockCompare } from '../../api/client'
const props = defineProps<{ stock: FinStockCompare }>()
const c = computed(() => props.stock.card)
function money(v?:number|null) { return v == null ? '—' : Math.abs(v) >= 1e8 ? `${(v/1e8).toFixed(2)} 亿` : `${(v/1e4).toFixed(1)} 万` }
function pct(v?:number|null, signed=false) { return v == null ? '—' : `${signed && v>0 ? '+' : ''}${(v*100).toFixed(1)}%` }
function ratio(v?:number|null) { return v == null ? '—' : `${v.toFixed(2)} 倍` }
const story = computed(() => {
  const m = c.value
  if (m.net_profit == null && m.revenue == null && m.ncf == null) return ['该报告期数据缺失，请选择其他报告期。']
  const lines = []
  if (m.revenue_yoy != null && m.net_profit_yoy != null) lines.push(m.revenue_yoy>0 && m.net_profit_yoy>0 ? '营收与净利润同比均增长。' : m.revenue_yoy>0 && m.net_profit_yoy<0 ? '营收增长，但净利润下降。' : `营收同比 ${pct(m.revenue_yoy,true)}，净利润同比 ${pct(m.net_profit_yoy,true)}。`)
  else lines.push(`利润变化：${m.net_profit_state || '缺少同期数据'}。`)
  if (m.ncf != null) lines.push(m.ncf<0 ? '经营现金流为负，本期经营活动净流出现金。' : m.net_profit != null && m.net_profit>0 ? `经营现金流为正，约为归母净利润的 ${ratio(m.ncf_ratio)}。` : '经营现金流非负，利润非正或缺失时不以净现比评价。')
  return lines
})
</script>
<style scoped>
.card { background:#111827; border:1px solid #253045; border-radius:12px; padding:22px; min-width:0; font-variant-numeric:tabular-nums; }h2 { color:#fff; font-size:18px; margin:0 0 8px; }small,header span { color:#9ca3af; font-size:12px; font-weight:400; }header small { margin-left:8px; }.story { border-left:3px solid #60a5fa; padding:6px 12px; margin:18px 0; background:#152239; }.story p { line-height:1.8; margin:4px 0; }.grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }section { padding:14px; background:#0b1220; border-radius:8px; }section>span { color:#93c5fd; font-size:12px; }strong { display:block; font-size:24px; color:#fff; margin:12px 0; }p { color:#d1d5db; font-size:13px; line-height:1.7; }small { line-height:1.7; }.tags { display:flex; gap:6px; flex-wrap:wrap; margin:16px 0; }.tags span { padding:4px 8px; border-radius:4px; font-size:12px; }.good { background:#172554; color:#93c5fd; }.risk { background:#422006; color:#fbbf24; }footer { color:#9ca3af; font-size:12px; line-height:1.7; }@media(max-width:550px){.grid{grid-template-columns:1fr}.card{padding:16px}}
</style>
