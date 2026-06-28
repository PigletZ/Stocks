import { createRouter, createWebHistory } from 'vue-router'
import OverviewView from '../views/OverviewView.vue'
import StockListView from '../views/StockListView.vue'
import WatchlistView from '../views/WatchlistView.vue'
import StockDetailView from '../views/StockDetailView.vue'
import StrategyView from '../views/StrategyView.vue'
import LoginView from '../views/LoginView.vue'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { title: '登录', public: true },
    },
    {
      path: '/',
      name: 'overview',
      component: OverviewView,
      meta: { title: '概览' },
    },
    {
      path: '/stocks',
      name: 'stock-list',
      component: StockListView,
      meta: { title: '全市场股票', parent: 'a-shares' },
    },
    {
      path: '/watchlist',
      name: 'watchlist',
      component: WatchlistView,
      meta: { title: '自选股票', parent: 'a-shares' },
    },
    {
      path: '/stock/:code',
      name: 'stock-detail',
      component: StockDetailView,
      meta: { title: '股票详情' },
    },
    {
      path: '/strategies',
      name: 'strategies',
      component: StrategyView,
      meta: { title: '策略选股' },
    },
  ],
})

// 全局前置守卫：未登录访问受保护页面时跳转登录页
router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.public) {
    // 已登录时访问登录页，直接回首页
    if (to.name === 'login' && auth.isAuthenticated) {
      return { name: 'overview' }
    }
    return true
  }
  if (!auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  return true
})

export default router
