import { createRouter, createWebHistory } from 'vue-router'
const OverviewView = () => import('../views/OverviewView.vue')
const StockListView = () => import('../views/StockListView.vue')
const WatchlistView = () => import('../views/WatchlistView.vue')
const StockDetailView = () => import('../views/StockDetailView.vue')
const EtfListView = () => import('../views/EtfListView.vue')
const FinancialAnalysisView = () => import('../views/FinancialAnalysisView.vue')
const ReviewWorkbenchView = () => import('../views/ReviewWorkbenchView.vue')
const JournalView = () => import('../views/JournalView.vue')
const SystemView = () => import('../views/SystemView.vue')
const LoginView = () => import('../views/LoginView.vue')
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
      path: '/review',
      name: 'review-workbench',
      component: ReviewWorkbenchView,
      meta: { title: '复盘工作台', parent: 'review' },
    },
    {
      path: '/review/ladder',
      name: 'limit-ladder',
      redirect: to => ({ name: 'overview', query: { ...to.query, tab: 'ladder' } }),
      meta: { title: '连板天梯', parent: 'overview' },
    },
    {
      path: '/review/emotion',
      name: 'emotion',
      redirect: to => ({ name: 'review-workbench', query: { ...to.query, section: 'emotion' }, hash: '#emotion' }),
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
      meta: { title: '系统管理' },
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
