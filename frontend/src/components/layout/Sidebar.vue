<template>
  <aside class="sidebar">
    <div class="logo">Stocks</div>
    <nav class="nav">
      <router-link to="/" class="nav-item" :class="{ active: $route.name === 'overview' }">
        <span class="icon">📊</span>
        <span>概览</span>
      </router-link>

      <router-link to="/strategies" class="nav-item" :class="{ active: $route.name === 'strategies' }">
        <span class="icon">🎯</span>
        <span>策略选股</span>
      </router-link>

      <div class="nav-group">
        <div class="nav-group-title" @click="aSharesExpanded = !aSharesExpanded">
          <span>A 股</span>
          <span class="arrow" :class="{ expanded: aSharesExpanded }">▶</span>
        </div>
        <div v-show="aSharesExpanded" class="nav-sub">
          <router-link to="/stocks" class="nav-item" :class="{ active: $route.name === 'stock-list' }">
            全市场股票
          </router-link>
          <router-link to="/watchlist" class="nav-item" :class="{ active: $route.name === 'watchlist' }">
            自选股票
          </router-link>
        </div>
      </div>
    </nav>

    <div class="sidebar-footer">
      <span class="user">👤 {{ auth.username || 'root' }}</span>
      <button class="logout" @click="onLogout">退出登录</button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'

const aSharesExpanded = ref(true)
const router = useRouter()
const auth = useAuthStore()

function onLogout() {
  auth.logout()
  router.replace({ name: 'login' })
}
</script>

<style scoped>
.sidebar {
  width: 220px;
  flex-shrink: 0;
  background: #111827;
  border-right: 1px solid #1f2937;
  display: flex;
  flex-direction: column;
  padding: 16px 0;
}

.logo {
  font-size: 20px;
  font-weight: 700;
  color: #60a5fa;
  padding: 0 20px 20px;
  border-bottom: 1px solid #1f2937;
  margin-bottom: 12px;
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0 12px;
}

.sidebar-footer {
  margin-top: auto;
  padding: 12px;
  border-top: 1px solid #1f2937;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sidebar-footer .user {
  font-size: 13px;
  color: #9ca3af;
  padding: 0 4px;
}

.logout {
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid #374151;
  background: #1f2937;
  color: #d1d5db;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.logout:hover {
  background: #ef4444;
  border-color: #ef4444;
  color: #fff;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 6px;
  color: #d1d5db;
  text-decoration: none;
  font-size: 14px;
  transition: all 0.2s;
}

.nav-item:hover {
  background: #1f2937;
  color: #fff;
}

.nav-item.active {
  background: #2563eb;
  color: #fff;
}

.icon {
  font-size: 16px;
}

.nav-group {
  display: flex;
  flex-direction: column;
}

.nav-group-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  color: #9ca3af;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  cursor: pointer;
  user-select: none;
}

.nav-group-title:hover {
  color: #d1d5db;
}

.arrow {
  font-size: 10px;
  transition: transform 0.2s;
}

.arrow.expanded {
  transform: rotate(90deg);
}

.nav-sub {
  display: flex;
  flex-direction: column;
  padding-left: 8px;
}

.nav-sub .nav-item {
  font-size: 13px;
  padding: 8px 12px;
}
</style>
