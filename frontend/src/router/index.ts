import { createRouter, createWebHistory } from 'vue-router'
import OverviewView from '../views/OverviewView.vue'
import StockListView from '../views/StockListView.vue'
import WatchlistView from '../views/WatchlistView.vue'
import StockDetailView from '../views/StockDetailView.vue'
import EtfListView from '../views/EtfListView.vue'
import FinancialAnalysisView from '../views/FinancialAnalysisView.vue'
import LimitLadderView from '../views/LimitLadderView.vue'
import EmotionView from '../views/EmotionView.vue'
import JournalView from '../views/JournalView.vue'
import SystemView from '../views/SystemView.vue'
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
      path: '/financial',
      name: 'financial',
      component: FinancialAnalysisView,
      meta: { title: '财务分析' },
    },
    {
      path: '/review/ladder',
      name: 'limit-ladder',
      component: LimitLadderView,
      meta: { title: '连板梯队', parent: 'review' },
    },
    {
      path: '/review/emotion',
      name: 'emotion',
      component: EmotionView,
      meta: { title: '情绪周期', parent: 'review' },
    },
    {
      path: '/review/journal',
      name: 'journal',
      component: JournalView,
      meta: { title: '复盘日志', parent: 'review' },
    },
    {
      path: '/etfs',
      name: 'etf-list',
      component: EtfListView,
      meta: { title: '全 ETF 列表', parent: 'etf' },
    },
    {
      path: '/etfs/gainers',
      name: 'etf-gainers',
      redirect: '/etfs',
      meta: { title: 'ETF 涨幅榜', parent: 'etf' },
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
    {
      path: '/system',
      name: 'system',
      component: SystemView,
      meta: { title: '系统监控' },
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
