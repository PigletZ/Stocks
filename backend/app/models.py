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


class StrategyPickCache(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("strategy_id", "trade_date", name="uix_strategy_pick_cache"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    strategy_id: str = Field(index=True)
    trade_date: date = Field(index=True)
    data_json: str = Field(default="[]")
    created_at: datetime = Field(default_factory=datetime.utcnow)
