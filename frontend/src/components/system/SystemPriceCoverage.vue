<template>
  <section class="coverage-panel"><h2>区间复权是否可用</h2><p>只读取本地报价、因子和官方日历，不发起行情请求。缺少任意端点的报价或因子，相关变化保持未知。</p>
    <div class="coverage-grid"><article v-for="item in items" :key="item.key"><header><h3>{{ item.label }}</h3><span :class="item.status">{{ labels[item.status] || '待核验' }}</span></header><p>实际核对 {{ item.effective_date || '暂无报价' }} · 应有 {{ item.expected_date || '待日历确认' }}</p><p>{{ item.message }}</p>
      <table><thead><tr><th>区间 / 基准日</th><th>因子齐全 / 有报价对</th><th>缺因子</th></tr></thead><tbody><tr v-for="row in item.windows" :key="row.days"><td>{{ row.days }} 日<small>{{ row.base_date || '日历不足' }}</small></td><td>{{ row.total ? `${row.valid.toLocaleString()} / ${row.total.toLocaleString()}` : '暂无有效样本' }}<small v-if="row.coverage_pct!==null">{{ row.coverage_pct }}%</small></td><td :class="{partial:row.missing_factors>0}">{{ row.total ? row.missing_factors : '—' }}</td></tr></tbody></table><small class="note">{{ item.note }}</small>
    </article></div>
  </section>
</template>
<script setup lang="ts">
import type { PriceCoverage } from '../../api/client'
defineProps<{items:PriceCoverage[]}>()
const labels:Record<string,string>={ok:'报价对因子齐全',partial:'部分因子缺失',stale:'报价滞后',unknown:'待核验'}
</script>
<style scoped>
.coverage-panel{padding:22px;border:1px solid #263449;border-radius:12px;background:#111a2b;color:#e2e8f0}.coverage-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}article{min-width:0;padding:18px;background:#0c1423;border:1px solid #253248;border-radius:9px}header{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}h2{font-size:16px;margin:0}h3{font-size:14px;margin:0}p,small{font-size:12px;color:#94a3b8;line-height:1.8}header span{font-size:11px;color:#94a3b8}header .ok{color:#6ee7b7}.partial,.stale{color:#fcd38b}table{width:100%;font-size:12px;border-collapse:collapse}th,td{padding:12px 5px;text-align:left;border-bottom:1px solid #243247}th{color:#94a3b8;font-weight:400}small{display:block;font-size:11px}.note{margin-top:12px}@media(max-width:900px){.coverage-grid{grid-template-columns:1fr}}
</style>
