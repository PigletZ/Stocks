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

export interface WatchlistPosition {
  quantity: number
  cost_price: number
  source: 'journal' | 'manual'
  unrealized_pnl: number | null
  unrealized_pct: number | null
  realized_pnl: number | null
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
  position?: WatchlistPosition | null
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

export interface DashboardSnapshot {
  date: string
  up: number | null
  down: number | null
  flat: number | null
  total: number | null
  up_ratio: number | null
  total_turnover: number | null
  limit_up: number
  limit_down: number
  opened_limit: number
  break_rate: number | null
}

export interface DashboardSector extends SectorDailyItem {
  rank: number
  rank_change: number | null
}

export interface OverviewDashboard {
  date: string
  latest_date: string | null
  available_dates: string[]
  status: 'ready' | 'partial' | 'missing'
  updated_at: string | null
  current: DashboardSnapshot | null
  previous: DashboardSnapshot | null
  history: DashboardSnapshot[]
  turnover_average: number | null
  turnover_average_days: number
  indices: IndexSpot[]
  short_term: {
    ready: boolean
    first_board: number | null
    second_board: number | null
    higher_board: number | null
    max_board: number | null
    leaders: { code: string; name: string; boards: number }[]
    previous_count: number | null
    promoted: number | null
    promote_rate: number | null
    avg_pct: number | null
    quote_samples: number
  }
  sectors: { industry: DashboardSector[]; concept: DashboardSector[] }
}

export async function fetchOverviewDashboard(date?: string, signal?: AbortSignal): Promise<OverviewDashboard> {
  const { data } = await api.get('/overview/dashboard', { params: { date }, signal })
  return data
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

export interface EtfObservation {
  code: string; name: string; category: string; benchmark: string; management: string
  close: number; amount: number; change_pct: number | null
  gain_2: number | null; gain_5: number | null; gain_10: number | null; gain_20: number | null
  state: string
}
export interface EtfDirection {
  category: string; count: number; samples_5: number; positive_5: number
  median_5: number | null; median_20: number | null; representative: string; amount: number
}
export interface EtfDashboard {
  target_date: string; effective_date: string; base_dates: Record<string, string | null>
  min_amount: number; quoted_count: number; items: EtfObservation[]; directions: EtfDirection[]; missing_windows: number[]
}
export async function fetchEtfDashboard(date: string, minAmount: number, signal?: AbortSignal): Promise<EtfDashboard> {
  const { data } = await api.get('/etfs/dashboard', { params: { date, min_amount: minAmount }, signal, timeout: 120000 })
  return data
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
  two_day: EtfGainerItem[]
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

export interface StockDailyHistoryItem {
  trade_date: string
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  amount?: number
  change_pct?: number
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

export async function fetchStockDailyHistory(
  code: string,
  start?: string,
  end?: string,
): Promise<StockDailyHistoryItem[]> {
  const { data } = await api.get(`/stocks/${code}/daily-history`, {
    params: { start, end },
  })
  return data
}

// ==================== 财务分析 ====================

export interface FinMetrics {
  net_profit_state?: string
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
  tags_by_period?: Record<string, FinTag[]>
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
  values: (number | null)[]
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

export interface FinHighlightItem {
  rank: number
  code: string
  name: string
  industry?: string | null
  good_count: number
  risk_count: number
  tags: FinTag[]
  metrics: FinMetrics & { period?: string }
}

export interface FinHighlightRank {
  date: string | null
  items: FinHighlightItem[]
}

export async function fetchFinancialHighlightRank(
  limit = 100,
  date?: string
): Promise<FinHighlightRank> {
  const { data } = await api.get('/financial/highlight-rank', {
    params: { limit, ...(date ? { date } : {}) },
  })
  return data
}

// ==================== 涨停复盘 ====================

export interface LimitLadderStock {
  code: string
  name: string
  boards: number
  up_stat?: string | null
  pct_chg?: number | null
  amount?: number | null
  fd_amount?: number | null
  first_time?: string | null
  open_times?: number | null
  float_mv?: number | null
}

export interface LimitLadderGroup {
  boards: number
  count: number
  stocks: LimitLadderStock[]
}

export interface LimitLadderResponse {
  trade_date: string | null
  ladder: LimitLadderGroup[]
  total: number
}

export async function fetchLimitLadder(date?: string): Promise<LimitLadderResponse> {
  const { data } = await api.get('/review/limit-ladder', { params: { date } })
  return data
}

export interface LimitPerfItem {
  code: string
  name: string
  prev_boards: number
  today_pct: number | null
  today_boards: number | null
  status: '晋级' | '炸板' | '红盘' | '绿盘' | '跌停' | '平盘' | '未知'
}

export interface LimitPerfStats {
  total: number
  promoted: number | null
  promote_rate: number | null
  opened: number | null
  limit_down: number | null
  avg_pct: number | null
}

export interface LimitPerfResponse {
  ready?: boolean
  trade_date: string | null
  prev_date: string | null
  stats: LimitPerfStats
  items: LimitPerfItem[]
}

export async function fetchLimitPerformance(date?: string): Promise<LimitPerfResponse> {
  const { data } = await api.get('/review/limit-performance', { params: { date } })
  return data
}

export interface ReviewObservation {
  id: number; code: string; name: string; observation_date: string; deadline: string
  reason: string; criterion: string; created_at: string; base_close: number | null; close: number | null
  price_change: number | null; verdict: string; explanation: string; verified_on: string | null; verified_at: string | null
}
export interface ReviewWorkbenchData {
  date: string; previous_date: string | null; available_dates: string[]; snapshot: DashboardSnapshot | null
  performance: LimitPerfResponse & {
    ready: boolean
    groups: { label: string; total: number; continued: number | null; rate: number | null }[]
    leaders: LimitPerfItem[]
    stats: LimitPerfStats & { median_pct: number | null; quote_samples: number; unknown: number }
  }
  structure: { ready: boolean; first: number | null; second: number | null; higher: number | null; highest: number | null }
  observations: ReviewObservation[]
}
export async function fetchReviewWorkbench(date?: string, signal?: AbortSignal): Promise<ReviewWorkbenchData> {
  const { data } = await api.get('/review/workbench', { params: { date }, signal })
  return data
}
export async function createReviewObservation(body: { code: string; observation_date: string; reason: string; criterion: string; deadline: string }) {
  const { data } = await api.post('/review/observations', body)
  return data
}
export async function verifyReviewObservation(id: number, date: string, verdict: string, explanation: string) {
  const { data } = await api.put(`/review/observations/${id}/verification`, { verdict, explanation }, { params: { date } })
  return data
}

export interface EmotionItem {
  date: string
  limit_up: number
  limit_down: number
  opened_limit: number
  break_rate: number | null
  promote_rate: number | null
  max_board: number | null
  up: number
  down: number
  total_turnover: number
}

export async function fetchEmotionSeries(start?: string, end?: string): Promise<EmotionItem[]> {
  const { data } = await api.get('/review/emotion', { params: { start, end } })
  return data
}

export async function syncReviewData(date?: string): Promise<{ trade_date: string; limit_count: number; dragon_count: number }> {
  const { data } = await api.post('/review/sync', null, { params: { date } })
  return data
}

// ==================== 复盘日志 / 交易台账 ====================

export interface ReviewNoteData {
  note_date: string
  content: string
  codes: string[]
  updated_at?: string
}

export async function fetchNote(date: string): Promise<ReviewNoteData> {
  const { data } = await api.get('/journal/note', { params: { date } })
  return data
}

export async function saveNote(date: string, content: string, codes: string[] = []): Promise<ReviewNoteData> {
  const { data } = await api.put('/journal/note', { content, codes }, { params: { date } })
  return data
}

export async function deleteNote(date: string): Promise<{ message: string }> {
  const { data } = await api.delete('/journal/note', { params: { date } })
  return data
}

export async function fetchNoteDates(year: number, month: number): Promise<{ note_dates: string[]; trade_dates: string[] }> {
  const { data } = await api.get('/journal/note-dates', { params: { year, month } })
  return data
}

export interface JournalTrade {
  id: number
  code: string
  name: string
  direction: 'buy' | 'sell'
  price: number
  quantity: number
  amount: number
  fee: number
  traded_at: string
  note?: string | null
}

export async function fetchJournalTrades(code?: string, start?: string, end?: string): Promise<JournalTrade[]> {
  const { data } = await api.get('/journal/trades', { params: { code, start, end } })
  return data
}

export interface JournalTradeInput {
  stock_code: string
  direction: 'buy' | 'sell'
  price: number
  quantity: number
  fee: number
  traded_at: string
  note?: string | null
}

export async function createJournalTrade(trade: JournalTradeInput): Promise<JournalTrade> {
  const { data } = await api.post('/journal/trades', trade)
  return data
}

export async function deleteJournalTrade(id: number): Promise<{ message: string }> {
  const { data } = await api.delete(`/journal/trades/${id}`)
  return data
}

export interface PositionItem {
  code: string
  name: string
  quantity: number
  cost_price: number
  close: number | null
  unrealized_pnl: number | null
  unrealized_pct: number | null
  realized_pnl: number | null
}

export async function fetchPositions(): Promise<PositionItem[]> {
  const { data } = await api.get('/journal/positions')
  return data
}

export interface JournalStats {
  total_realized: number | null
  incomplete_sell_count?: number
  win_count: number
  loss_count: number
  win_rate: number | null
  sell_count: number
  buy_count: number
  total_fee: number
}

export async function fetchJournalStats(): Promise<JournalStats> {
  const { data } = await api.get('/journal/stats')
  return data
}

// ==================== 手动持仓 ====================

export async function upsertHolding(code: string, costPrice: number, quantity: number, note?: string): Promise<{ code: string; cost_price: number; quantity: number }> {
  const { data } = await api.put(`/watchlist/holdings/${code}`, { cost_price: costPrice, quantity, note })
  return data
}

export async function deleteHolding(code: string): Promise<{ message: string }> {
  const { data } = await api.delete(`/watchlist/holdings/${code}`)
  return data
}

// ==================== 系统监控 ====================

export interface SystemDbInfo {
  path: string | null
  size_bytes: number | null
  size_mb: number | null
}

export interface TableFreshness {
  label: string
  table: string
  max_date: string | null
  rows: number
  age_days?: number
  status: 'ok' | 'stale' | 'empty'
}

export interface CronJobHealth {
  name: string
  schedule: string
  log: string
  last_run: string | null
  age_hours: number | null
  status: 'ok' | 'stale' | 'error' | 'missing'
  last_lines: string[]
  error: string | null
}

export interface SystemStatus {
  generated_at: string
  database: SystemDbInfo
  tables: TableFreshness[]
  cron_jobs: CronJobHealth[]
}

export async function fetchSystemStatus(): Promise<SystemStatus> {
  const { data } = await api.get('/system/status')
  return data
}
