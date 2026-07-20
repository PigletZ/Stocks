import axios from 'axios'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 30000,
})

const TOKEN_KEY = 'stocks_auth_token'

// 请求拦截器：自动附带登录 token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：401（未登录/过期）时清除登录态并跳转登录页
api.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem('stocks_auth_exp')
      localStorage.removeItem('stocks_auth_user')
      if (window.location.pathname !== '/login') {
        const redirect = encodeURIComponent(
          window.location.pathname + window.location.search
        )
        window.location.href = `/login?redirect=${redirect}`
      }
    }
    return Promise.reject(error)
  }
)

export interface Stock {
  id?: number
  code: string
  name: string
  market: string
  exchange: string
  industry?: string
  list_date?: string
}

export interface Bar {
  id?: number
  stock_code: string
  timestamp: string
  interval: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  adjusted: boolean
}

export interface StockListItem {
  code: string
  name: string
  exchange: string
  industry?: string
  list_date?: string
  quote_date?: string
  close?: number
  change_pct?: number
  amount?: number
  turnover_rate?: number
  turnover_rate_f?: number
  float_mv?: number
  total_mv?: number
  pe?: number
  pe_ttm?: number
  pb?: number
  ps?: number
  ps_ttm?: number
  dv_ratio?: number
  dv_ttm?: number
}

export interface PaginatedStockList {
  items: StockListItem[]
  total: number
  page: number
  page_size: number
}

export interface WatchlistItem {
  code: string
  name: string
  exchange: string
  group_id: number
  sort_order: number
  industry?: string
  quote_date?: string
  close?: number
  change_pct?: number
  amount?: number
  turnover_rate?: number
  float_mv?: number
  total_mv?: number
  pe?: number
  pb?: number
}

export interface WatchlistGroup {
  id: number
  name: string
  sort_order: number
  stocks: WatchlistItem[]
}

export async function fetchStockList(
  search?: string,
  industry?: string,
  page = 1,
  page_size = 50,
  sort_by = 'code',
  sort_order: 'asc' | 'desc' = 'asc',
): Promise<PaginatedStockList> {
  const { data } = await api.get('/stocks', {
    params: { search, industry, page, page_size, sort_by, sort_order },
  })
  return data
}

export async function fetchStock(code: string): Promise<StockListItem> {
  const { data } = await api.get(`/stocks/${code}`)
  return data
}

export async function fetchIndustries(): Promise<string[]> {
  const { data } = await api.get('/stocks/industries')
  return data
}

export async function syncStockList(): Promise<{ created: number; updated: number; total: number }> {
  const { data } = await api.post('/stocks/sync')
  return data
}

export async function syncDailyQuotes(trade_date?: string): Promise<{ date: string; count: number }> {
  const { data } = await api.post('/stocks/quotes/sync', null, {
    params: trade_date ? { trade_date } : undefined,
  })
  return data
}

export async function fetchStockCount(): Promise<{ count: number }> {
  const { data } = await api.get('/stocks/meta/count')
  return data
}

export async function syncBars(code: string, interval: string, start?: string, end?: string): Promise<{ count: number }> {
  const { data } = await api.post(`/bars/${code}/sync`, null, {
    params: { interval, start, end },
  })
  return data
}

export interface IndexSpot {
  code: string
  name: string
  price: number
  change: number
  change_pct: number
}

export interface MarketSummary {
  up: number
  down: number
  flat: number
  total: number
  limit_up: number
  limit_down: number
  opened_limit: number
  total_turnover: number
}

export interface RecentViewItem {
  code: string
  name: string
  exchange: string
  viewed_at: string
}

export async function fetchIndices(): Promise<IndexSpot[]> {
  const { data } = await api.get('/overview/indices')
  return data
}

export async function fetchMarketSummary(): Promise<MarketSummary> {
  const { data } = await api.get('/overview/market-summary')
  return data
}

export interface MarketHistoryItem {
  date: string
  up: number
  down: number
  flat: number
  total: number
  limit_up: number
  limit_down: number
  opened_limit: number
  total_turnover: number
}

export async function fetchMarketHistory(start?: string, end?: string): Promise<MarketHistoryItem[]> {
  const { data } = await api.get('/overview/market-history', {
    params: { start, end },
  })
  return data
}

export interface DailyOverview {
  date: string
  indices: IndexSpot[]
  market_stats: MarketSummary
}

export async function fetchDailyOverview(date?: string): Promise<DailyOverview> {
  const { data } = await api.get('/overview/daily-overview', {
    params: date ? { date } : undefined,
  })
  return data
}

export async function fetchTradeDates(start?: string, end?: string): Promise<string[]> {
  const { data } = await api.get('/overview/trade-dates', {
    params: { start, end },
  })
  return data
}

export interface RealtimeOverview {
  indices: IndexSpot[]
  market_stats: MarketSummary
  top_gainers: StockMover[]
  top_losers: StockMover[]
  industry_sectors: SectorDailyItem[]
  concept_sectors: SectorDailyItem[]
  speed_5min_up: SpeedRankingItem[]
  speed_5min_down: SpeedRankingItem[]
  speed_15min_up: SpeedRankingItem[]
  speed_15min_down: SpeedRankingItem[]
}

export interface StockMover {
  代码: string
  名称: string
  最新价: number
  涨跌幅: number
  成交额?: number
}

export interface SectorDailyItem {
  sector_code: string
  sector_name: string
  change_pct: number
  volume: number
}

export type SectorRankingDaily = {
  industry: SectorDailyItem[]
  concept: SectorDailyItem[]
}

export interface SpeedRankingItem {
  代码: string
  名称: string
  最新价: number
  涨跌幅: number
  speed_value: number
  speed_label: string
}

export interface LimitStock {
  代码: string
  名称: string
  最新价: number
  涨跌幅: number
  成交额: number
  封单比: number
  换手率: number
  流通值: number
  总市值: number
  首封时间: string | null
  封住时间: string | null
  开板次数: number
  涨停分析?: string
  跌停分析?: string
  几天几板: number
}

export interface LimitStockResponse {
  total: number
  items: LimitStock[]
}

export interface DragonTigerItem {
  代码: string
  名称: string
  上榜日: string
  收盘价: number
  涨跌幅: number
  龙虎榜净买额: number
  上榜原因: string
}

export async function fetchRealtimeOverview(): Promise<RealtimeOverview> {
  const { data } = await api.get('/overview/realtime')
  return data
}

export async function fetchLimitUpStocks(
  date?: string,
  sortBy: string = 'pct_chg',
  order: 'asc' | 'desc' = 'desc',
  offset = 0,
  limit = 20,
): Promise<LimitStockResponse> {
  const { data } = await api.get('/overview/limit-up', {
    params: { date, sort_by: sortBy, order, offset, limit },
  })
  return data
}

export async function fetchLimitDownStocks(
  date?: string,
  sortBy: string = 'pct_chg',
  order: 'asc' | 'desc' = 'asc',
  offset = 0,
  limit = 20,
): Promise<LimitStockResponse> {
  const { data } = await api.get('/overview/limit-down', {
    params: { date, sort_by: sortBy, order, offset, limit },
  })
  return data
}

export async function fetchOpenedLimitStocks(
  date?: string,
  sortBy: string = 'pct_chg',
  order: 'asc' | 'desc' = 'desc',
  offset = 0,
  limit = 20,
): Promise<LimitStockResponse> {
  const { data } = await api.get('/overview/opened-limit', {
    params: { date, sort_by: sortBy, order, offset, limit },
  })
  return data
}

export interface DragonTigerResponse {
  total: number
  items: DragonTigerItem[]
}

export async function fetchDragonTiger(
  date?: string,
  sortBy: 'change_pct' | 'net_amount' | 'trade_date' = 'net_amount',
  order: 'asc' | 'desc' = 'desc',
  offset = 0,
  limit = 20,
): Promise<DragonTigerResponse> {
  const { data } = await api.get('/overview/dragon-tiger', {
    params: { date, sort_by: sortBy, order, offset, limit },
  })
  return data
}

export interface TopGainerItem {
  rank: number
  code: string
  name: string
  close: number
  gain: number
  amount: number
  turnover_rate: number
  industry: string
}

export interface TopGainersResponse {
  target_date: string
  effective_date: string
  five_day: TopGainerItem[]
  ten_day: TopGainerItem[]
  twenty_day: TopGainerItem[]
}

export async function fetchTopGainers(date?: string): Promise<TopGainersResponse> {
  const { data } = await api.get('/overview/top-gainers', {
    params: date ? { date } : undefined,
  })
  return data
}

export interface EtfItem {
  code: string
  name: string
  management: string
  fund_type: string
  benchmark: string
  category: string
  close: number
  change_pct: number
  amount: number
}

export interface EtfListResponse {
  total: number
  items: EtfItem[]
  effective_date: string
}

export async function fetchEtfList(
  sortBy: string = 'change_pct',
  order: 'asc' | 'desc' = 'desc',
  offset = 0,
  limit = 50,
  category = '',
): Promise<EtfListResponse> {
  const { data } = await api.get('/etfs/list', {
    params: { sort_by: sortBy, order, offset, limit, category },
  })
  return data
}

export async function fetchEtfCategories(): Promise<string[]> {
  const { data } = await api.get('/etfs/categories')
  return data
}

export interface EtfGainerItem {
  rank: number
  code: string
  name: string
  close: number
  gain: number
}

export interface EtfGainersResponse {
  target_date: string
  effective_date: string
  five_day: EtfGainerItem[]
  ten_day: EtfGainerItem[]
  twenty_day: EtfGainerItem[]
}

export async function fetchEtfGainers(date?: string, category = ''): Promise<EtfGainersResponse> {
  const { data } = await api.get('/etfs/gainers', {
    params: { date, category },
  })
  return data
}

export async function fetchSectorRanking(
  type: 'industry' | 'concept' = 'industry',
  limit = 20,
): Promise<SectorDailyItem[]> {
  const { data } = await api.get('/overview/sectors', {
    params: { type, limit },
  })
  return data
}

export async function fetchSectorRankingDaily(
  date?: string,
  type: 'all' | 'industry' | 'concept' = 'all',
  sortBy: 'change_pct' | 'volume' = 'change_pct',
  limit = 50,
): Promise<SectorRankingDaily> {
  const { data } = await api.get('/overview/sectors-daily', {
    params: { date, type, sort_by: sortBy, limit },
  })
  return data
}

export async function syncSectorRankingDaily(
  date?: string,
  type: 'all' | 'industry' | 'concept' = 'all',
): Promise<{ date: string; counts: Record<string, number> }> {
  const { data } = await api.post('/overview/sync-sectors', null, {
    params: { date, type },
  })
  return data
}

export async function fetchSpeedRanking(
  interval: string = '5min',
  direction: string = 'up',
  limit = 20,
): Promise<SpeedRankingItem[]> {
  const { data } = await api.get('/overview/speed-ranking', {
    params: { interval, direction, limit },
  })
  return data
}

export async function fetchRecentViews(limit = 10): Promise<RecentViewItem[]> {
  const { data } = await api.get('/overview/recent-views', {
    params: { limit },
  })
  return data
}

export async function recordRecentView(code: string): Promise<{ message: string }> {
  const { data } = await api.post(`/overview/recent-views/${code}`)
  return data
}

export async function fetchWatchlistPreview(limit = 6): Promise<Omit<WatchlistItem, 'sort_order'>[]> {
  const { data } = await api.get('/overview/watchlist-preview', {
    params: { limit },
  })
  return data
}

export async function fetchIndexBars(code: string, start?: string, end?: string): Promise<Bar[]> {
  const { data } = await api.get(`/overview/index-bars/${code}`, {
    params: { start, end },
  })
  return data
}

export async function syncDailyOverview(date?: string): Promise<{ date: string; indices_count: number; market_stats: MarketSummary }> {
  const { data } = await api.post('/overview/sync-daily', null, {
    params: date ? { date } : undefined,
  })
  return data
}

export async function fetchWatchlistGroups(): Promise<WatchlistGroup[]> {
  const { data } = await api.get('/watchlist/groups')
  return data
}

export async function createWatchlistGroup(name: string, sort_order = 0): Promise<WatchlistGroup> {
  const { data } = await api.post('/watchlist/groups', null, {
    params: { name, sort_order },
  })
  return data
}

export async function renameWatchlistGroup(id: number, name: string): Promise<WatchlistGroup> {
  const { data } = await api.put(`/watchlist/groups/${id}`, null, {
    params: { name },
  })
  return data
}

export async function deleteWatchlistGroup(id: number): Promise<{ message: string }> {
  const { data } = await api.delete(`/watchlist/groups/${id}`)
  return data
}

export async function addToWatchlist(code: string, groupId?: number): Promise<{ code: string; group_id: number }> {
  const { data } = await api.post(`/watchlist/${code}`, null, {
    params: { group_id: groupId },
  })
  return data
}

export async function removeFromWatchlist(code: string): Promise<{ message: string }> {
  const { data } = await api.delete(`/watchlist/${code}`)
  return data
}

export async function moveWatchlistGroup(code: string, groupId: number): Promise<{ code: string; group_id: number }> {
  const { data } = await api.put(`/watchlist/${code}/group`, null, {
    params: { group_id: groupId },
  })
  return data
}

export async function fetchBars(code: string, interval: string, start?: string, end?: string): Promise<Bar[]> {
  const { data } = await api.get(`/bars/${code}`, {
    params: { interval, start, end },
  })
  return data
}

// ==================== 策略选股 ====================

export interface StrategyInfo {
  id: string
  name: string
  description: string
}

export interface StrategyPickItem {
  code: string
  name: string
  score: number
  buy_price: number
  reason: string
  extra?: Record<string, any>
}

export interface StrategyPicksResponse {
  strategy_id: string
  trade_date: string
  count: number
  items: StrategyPickItem[]
}

export async function fetchStrategies(): Promise<StrategyInfo[]> {
  const { data } = await api.get('/strategies')
  return data
}

export async function fetchStrategyPicks(
  strategyId: string,
  tradeDate?: string,
  forceRefresh?: boolean,
): Promise<StrategyPicksResponse> {
  const { data } = await api.get(`/strategies/${strategyId}/picks`, {
    params: { trade_date: tradeDate, force_refresh: forceRefresh },
  })
  return data
}

// ==================== 策略回测 ====================

export interface BacktestRequest {
  strategy_id: string
  start_date: string
  end_date: string
  window_days: number
  hold_days: number
  max_positions: number
  max_per_day: number
  require_dragon: boolean
  initial_capital: number
  commission_rate: number
}

export interface BacktestMetrics {
  initial_capital: number
  final_value: number
  total_return: number
  total_return_pct: number
  cagr: number
  cagr_pct: number
  max_drawdown: number
  max_drawdown_pct: number
  sharpe_ratio: number
  num_buy_trades: number
  num_sell_trades: number
  win_rate: number
  win_rate_pct: number
  profit_factor: number
  avg_trade_pnl: number
  avg_win: number
  avg_loss: number
  avg_hold_days: number
}

export interface BacktestTradeItem {
  id: number
  stock_code: string
  stock_name?: string
  direction: 'buy' | 'sell'
  quantity: number
  price: number
  amount: number
  commission: number
  trade_date: string
  signal_date?: string
  hold_days?: number
  pnl?: number
  raw?: Record<string, any>
}

export interface EquityPoint {
  date: string
  cash: number
  market_value: number
  total_value: number
}

export interface BacktestResult {
  id: number
  strategy_id: string
  start_date: string
  end_date: string
  initial_capital: number
  params: string
  status: string
  error_message?: string
  metrics: BacktestMetrics
  equity_curve: EquityPoint[]
  trades: BacktestTradeItem[]
  created_at: string
  completed_at?: string
}

export interface BacktestRunInfo {
  id: number
  strategy_id: string
  start_date: string
  end_date: string
  initial_capital: number
  params: string
  status: string
  error_message?: string
  metrics?: BacktestMetrics
  created_at: string
  completed_at?: string
}

export async function runBacktest(req: BacktestRequest): Promise<{ run_id: number; status: string }> {
  const { data } = await api.post('/backtests/run', req)
  return data
}

export async function fetchBacktest(runId: number): Promise<BacktestResult> {
  const { data } = await api.get(`/backtests/${runId}`)
  return data
}

export async function fetchBacktests(strategyId?: string, limit = 20): Promise<BacktestRunInfo[]> {
  const { data } = await api.get('/backtests', {
    params: { strategy_id: strategyId, limit },
  })
  return data
}

// ==================== 财务分析 ====================

export interface FinMetrics {
  revenue?: number | null
  revenue_yoy?: number | null
  net_profit?: number | null
  net_profit_yoy?: number | null
  gross_margin?: number | null
  net_margin?: number | null
  roe?: number | null
  roe_annualized?: number | null
  debt_ratio?: number | null
  current_ratio?: number | null
  ncf?: number | null
  ncf_ratio?: number | null
  inv_turnover?: number | null
  ar_turnover?: number | null
  asset_turnover?: number | null
  goodwill_ratio?: number | null
}

export interface FinTag {
  type: 'good' | 'risk'
  label: string
}

export interface FinStockCompare {
  code: string
  name: string
  industry?: string | null
  periods: string[]
  metrics: Record<string, FinMetrics>
  card: FinMetrics & { period?: string | null }
  tags: FinTag[]
}

export interface FinRadarSeries {
  name: string
  values: number[]
}

export interface FinCompareResult {
  stocks: FinStockCompare[]
  radar: { dims: string[]; series: FinRadarSeries[] }
}

export interface FinStatementItem {
  field: string
  name: string
  values: (number | null)[]
  yoy: (number | null)[]
}

export interface FinStatementResult {
  periods: string[]
  items: FinStatementItem[]
}

export async function fetchFinancialCompare(codes: string[]): Promise<FinCompareResult> {
  const { data } = await api.post('/financial/compare', { codes })
  return data
}

export async function fetchFinancialStatements(
  code: string,
  type: 'income' | 'balance' | 'cashflow'
): Promise<FinStatementResult> {
  const { data } = await api.get('/financial/statements', { params: { code, type } })
  return data
}
