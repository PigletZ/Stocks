<template>
  <div class="result-table">
    <div v-if="items.length === 0" class="empty">暂无选股结果</div>

    <!-- piglet 专属列布局 -->
    <table v-else-if="isPiglet">
      <thead>
        <tr>
          <th>排名</th>
          <th>股票</th>
          <th>首板日期</th>
          <th>不破天数</th>
          <th>游资介入</th>
          <th>龙虎榜净买</th>
          <th>参考价</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(item, index) in items" :key="item.code">
          <td class="rank">{{ index + 1 }}</td>
          <td>
            <div class="stock-name">{{ item.name }}</div>
            <div class="stock-code">{{ item.code }}</div>
          </td>
          <td>{{ formatDate(item.extra?.first_limit_date) }}</td>
          <td>{{ item.extra?.hold_days ?? '-' }}</td>
          <td>
            <span v-if="item.extra?.has_dragon" class="tag-dragon">游资</span>
            <span v-else class="tag-none">无</span>
          </td>
          <td>{{ formatYi(item.extra?.net_amount) }}</td>
          <td>{{ item.buy_price.toFixed(2) }}</td>
          <td>
            <button class="btn-link" @click="$emit('addWatchlist', item.code)">加自选</button>
            <router-link :to="`/stock/${item.code}`" class="btn-link">详情</router-link>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- 默认（评分类策略）列布局 -->
    <table v-else>
      <thead>
        <tr>
          <th>排名</th>
          <th>股票</th>
          <th>评分</th>
          <th>买入价</th>
          <th>推荐理由</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(item, index) in items" :key="item.code">
          <td class="rank">{{ index + 1 }}</td>
          <td>
            <div class="stock-name">{{ item.name }}</div>
            <div class="stock-code">{{ item.code }}</div>
          </td>
          <td>
            <span class="score" :style="scoreStyle(item.score)">{{ item.score.toFixed(2) }}</span>
          </td>
          <td>{{ item.buy_price.toFixed(2) }}</td>
          <td class="reason">{{ item.reason }}</td>
          <td>
            <button class="btn-link" @click="$emit('addWatchlist', item.code)">加自选</button>
            <router-link :to="`/stock/${item.code}`" class="btn-link">详情</router-link>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { StrategyPickItem } from '../../api/client'

const props = defineProps<{
  items: StrategyPickItem[]
  strategyId?: string
}>()

defineEmits<{
  (e: 'addWatchlist', code: string): void
}>()

const isPiglet = computed(() => props.strategyId === 'piglet')

function formatDate(d?: string) {
  if (!d) return '-'
  // 入参形如 2026-06-18，展示为 06-18
  return d.length >= 10 ? d.slice(5) : d
}

function formatYi(amount?: number | null) {
  if (amount === null || amount === undefined) return '-'
  return `${(amount / 1e8).toFixed(2)}亿`
}

function scoreStyle(score: number) {
  const ratio = score / 100
  const r = Math.round(239 + (34 - 239) * ratio)
  const g = Math.round(68 + (197 - 68) * ratio)
  const b = Math.round(68 + (94 - 68) * ratio)
  return {
    color: `rgb(${r}, ${g}, ${b})`,
    fontWeight: 600,
  }
}
</script>

<style scoped>
.result-table {
  background: #111827;
  border: 1px solid #1f2937;
  border-radius: 8px;
  overflow: hidden;
}

.empty {
  padding: 40px;
  text-align: center;
  color: #6b7280;
  font-size: 14px;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

th,
td {
  padding: 14px 16px;
  text-align: left;
  border-bottom: 1px solid #1f2937;
}

th {
  background: #0b0f19;
  color: #9ca3af;
  font-weight: 500;
  font-size: 13px;
}

td {
  color: #e5e7eb;
}

.rank {
  color: #9ca3af;
  font-weight: 600;
  width: 60px;
}

.stock-name {
  font-weight: 500;
  color: #fff;
}

.stock-code {
  font-size: 12px;
  color: #9ca3af;
  margin-top: 2px;
}

.reason {
  color: #d1d5db;
  line-height: 1.5;
  max-width: 400px;
}

.tag-dragon {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(239, 68, 68, 0.15);
  color: #f87171;
  font-size: 12px;
  font-weight: 600;
}

.tag-none {
  color: #6b7280;
  font-size: 12px;
}

.btn-link {
  background: transparent;
  border: none;
  color: #60a5fa;
  cursor: pointer;
  font-size: 13px;
  margin-right: 12px;
  padding: 0;
  text-decoration: none;
}

.btn-link:hover {
  text-decoration: underline;
}

@media (max-width: 900px) {
  .reason {
    max-width: 200px;
  }
}
</style>
