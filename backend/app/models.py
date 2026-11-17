from sqlmodel import Field, SQLModel
from sqlalchemy import UniqueConstraint
from datetime import datetime, date
from typing import Optional


class Stock(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(index=True, unique=True)
    name: str
    market: str = "A股"
    exchange: str  # SH / SZ / BJ
    industry: Optional[str] = None
    list_date: Optional[date] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None


class Bar(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("stock_code", "timestamp", "interval", name="uix_bar_stock_time_interval"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    stock_code: str = Field(index=True, foreign_key="stock.code")
    timestamp: datetime
    interval: str = Field(index=True)  # 1d
    open: float
    high: float
    low: float
    close: float
    volume: float
    adjusted: bool = False  # 是否已复权


class Annotation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    stock_code: str = Field(index=True, foreign_key="stock.code")
    timestamp: datetime
    type: str  # note / line / rect
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Trade(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)
    stock_code: str = Field(index=True, foreign_key="stock.code")
    direction: str  # buy / sell
    price: float
    quantity: int
    timestamp: datetime


class ReplaySession(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(index=True, unique=True)
    stock_code: str = Field(index=True, foreign_key="stock.code")
    start_date: datetime
    end_date: datetime
    initial_capital: float
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WatchlistGroup(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    sort_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WatchlistItem(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("stock_code", name="uix_watchlist_stock"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    stock_code: str = Field(index=True, foreign_key="stock.code")
    group_id: Optional[int] = Field(default=None, foreign_key="watchlistgroup.id")
    sort_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RecentView(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("stock_code", name="uix_recent_view_stock"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    stock_code: str = Field(index=True, foreign_key="stock.code")
    viewed_at: datetime = Field(default_factory=datetime.utcnow)


class MarketDailyStat(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("stat_date", name="uix_market_daily_stat_date"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    stat_date: date = Field(index=True)
    up: int = 0
    down: int = 0
    flat: int = 0
    limit_up: int = 0
    limit_down: int = 0
    opened_limit: int = 0
    total: int = 0
    total_turnover: float = 0.0
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class IndexDaily(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("code", "trade_date", name="uix_index_daily_code_date"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(index=True)
    name: str
    trade_date: date = Field(index=True)
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    change: float
    change_pct: float
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SectorDaily(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("sector_type", "sector_code", "trade_date", name="uix_sector_daily_type_code_date"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    sector_type: str = Field(index=True)  # industry / concept
    sector_code: str = Field(index=True)
    sector_name: str
    trade_date: date = Field(index=True)
    change_pct: float
    volume: float  # Tushare ths_daily 未提供成交额，此处存成交量（手）
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class StockDailyQuote(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("stock_code", "trade_date", name="uix_quote_stock_date"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    stock_code: str = Field(index=True, foreign_key="stock.code")
    trade_date: date = Field(index=True)

    close: Optional[float] = None
    change_pct: Optional[float] = None
    amount: Optional[float] = None

    turnover_rate: Optional[float] = None
    turnover_rate_f: Optional[float] = None
    float_mv: Optional[float] = None
    total_mv: Optional[float] = None

    pe: Optional[float] = None
    pe_ttm: Optional[float] = None
    pb: Optional[float] = None
    ps: Optional[float] = None
    ps_ttm: Optional[float] = None
    dv_ratio: Optional[float] = None
    dv_ttm: Optional[float] = None

    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ReviewNote(SQLModel, table=True):
    """每日复盘笔记（一天一篇）"""

    __table_args__ = (UniqueConstraint("note_date", name="uix_review_note_date"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    note_date: date = Field(index=True)
    content: str = ""                      # Markdown 文本
    codes_json: Optional[str] = None       # 关联股票代码列表 JSON，如 ["000001","600519"]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ReviewObservation(SQLModel, table=True):
    """有日期与原始依据的关注记录，原始判断不随验证改写。"""
    __tablename__ = "review_observation"
    __table_args__ = (UniqueConstraint("stock_code", "observation_date", name="uix_observation_code_date"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    stock_code: str = Field(index=True)
    observation_date: date = Field(index=True)
    reason: str
    criterion: str
    deadline: date
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ReviewVerification(SQLModel, table=True):
    __tablename__ = "review_verification"
    __table_args__ = (UniqueConstraint("observation_id", "review_date", name="uix_verification_observation_date"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    observation_id: int = Field(foreign_key="review_observation.id", index=True)
    review_date: date = Field(index=True)
    verdict: str
    explanation: str = ""
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Holding(SQLModel, table=True):
    """手动录入的持仓（无台账记录的股票；有台账的以 FIFO 计算为准）"""

    __table_args__ = (UniqueConstraint("stock_code", name="uix_holding_stock"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    stock_code: str = Field(index=True, foreign_key="stock.code")
    cost_price: float
    quantity: int
    note: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TradeJournal(SQLModel, table=True):
    """真实交易台账（手动录入的买卖记录）"""

    id: Optional[int] = Field(default=None, primary_key=True)
    stock_code: str = Field(index=True)
    direction: str                         # buy / sell
    price: float
    quantity: int
    fee: float = 0.0                       # 佣金+印花税等费用合计（元）
    traded_at: datetime = Field(index=True)
    note: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ScreenPreset(SQLModel, table=True):
    """通用选股器保存的条件组合（可作为自定义策略出现在策略选股页）"""

    __table_args__ = (UniqueConstraint("name", name="uix_screen_preset_name"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    conditions_json: str = "[]"           # [{field, op, value}]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class LimitUpDaily(SQLModel, table=True):
    """涨跌停/炸板明细缓存（Tushare limit_list_d，当天整体覆盖式写入）"""

    __table_args__ = (UniqueConstraint("stock_code", "trade_date", name="uix_limit_daily_code_date"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    stock_code: str = Field(index=True)
    trade_date: date = Field(index=True)
    name: str
    limit_type: str = Field(index=True)  # U涨停 / D跌停 / Z炸板
    close: Optional[float] = None
    pct_chg: Optional[float] = None
    amount: Optional[float] = None       # 成交额（元）
    fd_amount: Optional[float] = None    # 封单金额（元）
    turnover_ratio: Optional[float] = None
    float_mv: Optional[float] = None
    total_mv: Optional[float] = None
    first_time: Optional[str] = None     # 首次封板时间 HHMMSS
    last_time: Optional[str] = None      # 最后封板时间 HHMMSS
    open_times: Optional[int] = None     # 开板次数
    up_stat: Optional[str] = None        # 涨停统计，如 "2/3"
    limit_times: Optional[int] = None    # 连板数
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class DragonTigerDaily(SQLModel, table=True):
    """龙虎榜缓存（Tushare top_list，当天整体覆盖式写入）"""

    __table_args__ = (UniqueConstraint("stock_code", "trade_date", name="uix_dragon_tiger_code_date"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    stock_code: str = Field(index=True)
    trade_date: date = Field(index=True)
    name: str
    close: Optional[float] = None
    pct_change: Optional[float] = None
    turnover_rate: Optional[float] = None
    amount: Optional[float] = None       # 龙虎榜成交额（元）
    l_buy: Optional[float] = None        # 龙虎榜买入额（元）
    l_sell: Optional[float] = None       # 龙虎榜卖出额（元）
    net_amount: Optional[float] = None   # 龙虎榜净买额（元）
    net_rate: Optional[float] = None     # 净买额占总成交比
    reason: Optional[str] = None         # 上榜原因
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class StrategyPickCache(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("strategy_id", "trade_date", name="uix_strategy_pick_cache"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    strategy_id: str = Field(index=True)
    trade_date: date = Field(index=True)
    data_json: str = Field(default="[]")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BacktestRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    strategy_id: str = Field(index=True)
    start_date: date
    end_date: date
    initial_capital: float
    params_json: str = Field(default="{}")
    status: str = Field(default="pending")  # pending / running / completed / failed
    metrics_json: Optional[str] = None
    equity_curve_json: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


class BacktestTrade(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    backtest_run_id: int = Field(index=True, foreign_key="backtestrun.id")
    stock_code: str = Field(index=True)
    direction: str  # buy / sell
    quantity: int
    price: float
    amount: float  # 成交金额 = price * quantity
    commission: float
    trade_date: date
    signal_date: Optional[date] = None
    hold_days: Optional[int] = None
    pnl: Optional[float] = None  # 仅卖出时填写
    raw_json: Optional[str] = None  # 保留 first_limit_date / base_close / has_dragon 等
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FinIncome(SQLModel, table=True):
    """利润表（按报告期），常用字段建列 + data_json 存全科目原文"""

    __table_args__ = (UniqueConstraint("stock_code", "end_date", name="uix_fin_income_code_date"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    stock_code: str = Field(index=True, foreign_key="stock.code")
    end_date: date = Field(index=True)  # 报告期
    f_ann_date: Optional[date] = None  # 实际公告日（用于判断更新）
    total_revenue: Optional[float] = None  # 营业总收入
    revenue: Optional[float] = None  # 营业收入
    operate_cost: Optional[float] = None  # 营业成本
    n_income_attr_p: Optional[float] = None  # 归母净利润
    basic_eps: Optional[float] = None  # 基本每股收益
    data_json: Optional[str] = None  # 全科目原文 JSON
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class FinBalance(SQLModel, table=True):
    """资产负债表（按报告期）"""

    __table_args__ = (UniqueConstraint("stock_code", "end_date", name="uix_fin_balance_code_date"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    stock_code: str = Field(index=True, foreign_key="stock.code")
    end_date: date = Field(index=True)
    f_ann_date: Optional[date] = None
    total_assets: Optional[float] = None  # 资产总计
    total_liab: Optional[float] = None  # 负债合计
    total_hldr_eqy_inc_min_int: Optional[float] = None  # 股东权益合计（含少数股东）
    total_hldr_eqy_exc_min_int: Optional[float] = None  # 归母股东权益
    total_cur_assets: Optional[float] = None  # 流动资产合计
    total_cur_liab: Optional[float] = None  # 流动负债合计
    money_cap: Optional[float] = None  # 货币资金
    inventories: Optional[float] = None  # 存货
    accounts_receiv: Optional[float] = None  # 应收账款
    goodwill: Optional[float] = None  # 商誉
    data_json: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class FinCashflow(SQLModel, table=True):
    """现金流量表（按报告期）"""

    __table_args__ = (UniqueConstraint("stock_code", "end_date", name="uix_fin_cashflow_code_date"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    stock_code: str = Field(index=True, foreign_key="stock.code")
    end_date: date = Field(index=True)
    f_ann_date: Optional[date] = None
    n_cashflow_act: Optional[float] = None  # 经营活动现金流净额
    n_cashflow_inv_act: Optional[float] = None  # 投资活动现金流净额
    n_cash_flows_fnc_act: Optional[float] = None  # 筹资活动现金流净额
    free_cashflow: Optional[float] = None  # 自由现金流
    data_json: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class FinHighlight(SQLModel, table=True):
    """每日亮点 Top100 榜单（stat_date 当天重算整体覆盖）"""

    __table_args__ = (UniqueConstraint("stat_date", "code", name="uix_fin_highlight_date_code"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    stat_date: date = Field(index=True)
    code: str = Field(index=True, foreign_key="stock.code")
    rank: int
    good_count: int = 0
    risk_count: int = 0
    tags_json: Optional[str] = None  # [{type, label}]
    metrics_json: Optional[str] = None  # 最新期核心指标快照
    updated_at: datetime = Field(default_factory=datetime.utcnow)
