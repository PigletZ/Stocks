"""同步策略选股所需的历史数据。

1. 同步最近 N 个交易日的 StockDailyQuote（全市场，按交易日批量）
2. 同步所有主板股票最近 M 天的 Bar 数据（逐只，带限流保护）
"""

import time
from datetime import date, datetime, timedelta
from typing import List

from sqlmodel import Session, select

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.database import engine
from app.models import Bar, Stock, StockDailyQuote
from app.services.tushare_stock_service import TushareStockService


def sync_daily_quotes(days: int = 30) -> None:
    """同步最近 N 个交易日的全市场日行情。"""
    service = TushareStockService()
    pro = service._get_tushare_pro()

    end_date = date.today()
    start_date = end_date - timedelta(days=days * 2)

    df_cal = pro.trade_cal(
        exchange="SSE",
        start_date=start_date.strftime("%Y%m%d"),
        end_date=end_date.strftime("%Y%m%d"),
        is_open="1",
    )
    if df_cal is None or df_cal.empty:
        print("未获取到交易日历")
        return

    trade_dates = sorted(df_cal["cal_date"].astype(str).tolist())
    trade_dates = trade_dates[-days:]

    print(f"开始同步 {len(trade_dates)} 个交易日的 StockDailyQuote...")

    with Session(engine) as session:
        for date_str in trade_dates:
            trade_date = datetime.strptime(date_str, "%Y%m%d").date()
            quotes = service.fetch_daily_quotes(trade_date)

            for quote in quotes:
                existing = session.exec(
                    select(StockDailyQuote)
                    .where(StockDailyQuote.stock_code == quote.stock_code)
                    .where(StockDailyQuote.trade_date == quote.trade_date)
                ).first()
                if existing:
                    for field in [
                        "close", "change_pct", "amount", "turnover_rate", "turnover_rate_f",
                        "float_mv", "total_mv", "pe", "pe_ttm", "pb", "ps", "ps_ttm",
                        "dv_ratio", "dv_ttm",
                    ]:
                        setattr(existing, field, getattr(quote, field))
                    existing.updated_at = datetime.utcnow()
                    session.add(existing)
                else:
                    session.add(quote)

            session.commit()
            print(f"  {trade_date}: {len(quotes)} 只股票")

    print("StockDailyQuote 同步完成")


def sync_bars(days: int = 365, sleep_seconds: float = 0.3) -> None:
    """同步所有主板股票最近 N 天的 Bar 数据。"""
    service = TushareStockService()

    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    with Session(engine) as session:
        stocks = session.exec(select(Stock)).all()

    # 过滤主板
    main_board_codes = [
        s.code for s in stocks
        if (s.code.startswith("60") or s.code.startswith("00"))
        and not s.code.startswith("688")
        and not s.code.startswith("300")
        and not s.code.startswith("301")
    ]

    print(f"开始同步 {len(main_board_codes)} 只主板股票的 Bar 数据（{start_date} ~ {end_date}）...")

    with Session(engine) as session:
        for i, code in enumerate(main_board_codes, 1):
            try:
                bars = service.fetch_daily_bars(code, start=start_date, end=end_date)
                if not bars:
                    continue

                min_ts = min(b.timestamp for b in bars)
                max_ts = max(b.timestamp for b in bars)

                old_bars = session.exec(
                    select(Bar)
                    .where(Bar.stock_code == code)
                    .where(Bar.interval == "1d")
                    .where(Bar.timestamp >= min_ts)
                    .where(Bar.timestamp <= max_ts)
                ).all()
                for old in old_bars:
                    session.delete(old)

                for bar in bars:
                    session.add(bar)
                session.commit()

                if i % 50 == 0:
                    print(f"  已同步 {i}/{len(main_board_codes)} 只股票")

                time.sleep(sleep_seconds)
            except Exception as e:
                print(f"  同步 {code} 失败: {e}")
                continue

    print("Bar 同步完成")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="同步策略选股所需历史数据")
    parser.add_argument("--quote-days", type=int, default=30, help="同步日行情天数")
    parser.add_argument("--bar-days", type=int, default=365, help="同步 K 线天数")
    parser.add_argument("--bar-sleep", type=float, default=0.3, help="K 线同步间隔秒数")
    parser.add_argument("--skip-bars", action="store_true", help="跳过 K 线同步")
    args = parser.parse_args()

    sync_daily_quotes(args.quote_days)

    if not args.skip_bars:
        sync_bars(args.bar_days, args.bar_sleep)


if __name__ == "__main__":
    main()
