from datetime import date
from typing import Dict, List, Optional, Tuple

from sqlmodel import Session, select

from ..models import Stock
from ..services.tushare_stock_service import TushareStockService
from ..strategies.base import StockPick, StrategyBase, register_strategy
from ..strategies.filters import apply_base_filters
from .piglet_provider import PigletDataProvider, TusharePigletProvider


@register_strategy
class PigletStrategy(StrategyBase):
    """首板不破·龙头跟踪策略（piglet）。

    捕捉最近 window_days 个交易日内首次涨停后、后续每个交易日最低价均不跌破
    首板收盘价的强势龙头股；并标注窗口内是否有龙虎榜游资介入。
    """

    strategy_id = "piglet"
    strategy_name = "首板不破·龙头跟踪"
    description = "近N日首次涨停后股价持续不破首板收盘价的强势龙头，标注龙虎榜游资介入。"

    def __init__(
        self,
        window_days: int = 5,
        provider: Optional[PigletDataProvider] = None,
    ):
        self.window_days = window_days
        self.provider = provider or TusharePigletProvider()

    def select(self, trade_date: date, session: Session) -> List[StockPick]:
        trade_dates = self.provider.get_trade_dates(trade_date, self.window_days)
        if len(trade_dates) < 2:
            # 不足两个交易日，无法验证"首板之后不破"
            return []

        # 1. 构建涨停池，记录每只股票的首板日与首板收盘价（base_close）
        first_limit: Dict[str, Tuple[date, float]] = {}  # code -> (首板日, 首板收盘价)
        for d in trade_dates:
            df = self.provider.get_limit_list(d)
            if df is None or df.empty:
                continue
            df = df[df["limit"] == "U"].copy()
            for _, row in df.iterrows():
                code = TushareStockService._ts_code_to_code(row["ts_code"])
                if not code:
                    continue
                base_close = TusharePigletProvider._safe_float(row.get("close"))
                if base_close is None or base_close <= 0:
                    continue
                # trade_dates 已按时间升序遍历，首次出现即为首板日
                if code not in first_limit:
                    first_limit[code] = (d, base_close)

        if not first_limit:
            return []

        # 2. 公共过滤：ST、科创板、创业板、北交所、次新股
        candidate_codes = apply_base_filters(list(first_limit.keys()), trade_date, session)
        if not candidate_codes:
            return []

        # 3. 取窗口内每日最低价 {(code, date): low}，以及最新收盘价 {code: close}
        last_date = trade_dates[-1]
        low_map, latest_close_map = self.provider.get_lows_and_close(
            trade_dates, set(candidate_codes)
        )

        # 4. 首板不破：首板日之后每个交易日 low >= base_close
        survivors: List[Dict] = []
        for code in candidate_codes:
            fld, base_close = first_limit[code]
            # 首板就在最近交易日，无后续交易日可验证 -> 当日不纳入
            if fld >= last_date:
                continue
            follow_dates = [d for d in trade_dates if d > fld]
            ok = True
            for d in follow_dates:
                low = low_map.get((code, d))
                if low is None or low < base_close:
                    ok = False
                    break
            if ok and follow_dates:
                survivors.append(
                    {
                        "code": code,
                        "first_limit_date": fld,
                        "base_close": base_close,
                        "hold_days": len(follow_dates),
                    }
                )

        if not survivors:
            return []

        # 5. 龙虎榜增强标记：窗口内是否上榜 + 净买额合计
        net_amount_map = self.provider.get_top_list_net(
            trade_dates, {s["code"] for s in survivors}
        )

        # 股票名称与所属行业
        codes = [s["code"] for s in survivors]
        stocks = session.exec(select(Stock).where(Stock.code.in_(codes))).all()
        name_map = {s.code: s.name for s in stocks}
        industry_map = {s.code: s.industry for s in stocks}

        picks: List[StockPick] = []
        for s in survivors:
            code = s["code"]
            fld: date = s["first_limit_date"]
            base_close: float = s["base_close"]
            hold_days: int = s["hold_days"]
            net_amount = net_amount_map.get(code)  # 单位：元
            has_dragon = net_amount is not None

            # 首板至今涨幅：(最新收盘 - 首板收盘) / 首板收盘
            latest_close = latest_close_map.get(code)
            since_first_pct: Optional[float] = None
            if latest_close is not None and base_close:
                since_first_pct = (latest_close - base_close) / base_close * 100

            parts = [
                f"首板 {fld:%m-%d}（收盘 {base_close:.2f}）",
                f"其后 {hold_days} 个交易日最低价未破首板价",
            ]
            if since_first_pct is not None:
                parts.append(f"首板至今 {since_first_pct:+.2f}%")
            if has_dragon:
                parts.append(f"游资介入，龙虎榜净买 {net_amount / 1e8:.2f}亿")
            else:
                parts.append("无龙虎榜")
            reason = "，".join(parts)

            picks.append(
                StockPick(
                    code=code,
                    name=name_map.get(code, code),
                    score=0.0,  # 暂不评分
                    buy_price=base_close,  # 以首板收盘价作为参考价
                    reason=reason,
                    raw_data={
                        "first_limit_date": fld.isoformat(),
                        "base_close": base_close,
                        "hold_days": hold_days,
                        "has_dragon": has_dragon,
                        "net_amount": net_amount,
                        "latest_close": latest_close,
                        "since_first_pct": since_first_pct,
                        "industry": industry_map.get(code),
                    },
                )
            )

        # 排序：首板日升序（越早启动越强）-> 游资介入优先 -> 净买额降序
        picks.sort(
            key=lambda p: (
                p.raw_data["first_limit_date"],
                0 if p.raw_data["has_dragon"] else 1,
                -(p.raw_data["net_amount"] or 0),
            )
        )
        return picks
