#!/usr/bin/env python3
"""导入指定日期范围的日概览历史数据到数据库。

用法：
    cd /kimi/projects/Stocks/backend
    source venv/bin/activate
    python scripts/import_historical.py --start 2024-01-01 --end 2025-06-20

参数：
    --start  开始日期，格式 YYYY-MM-DD（默认两年前）
    --end    结束日期，格式 YYYY-MM-DD（默认今天）
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session
from app.database import engine
from app.services.overview_service import OverviewService


def parse_date(s: str) -> date:
    return date.fromisoformat(s)


def main():
    parser = argparse.ArgumentParser(description="导入日概览历史数据")
    parser.add_argument(
        "--start",
        type=parse_date,
        default=date.today() - timedelta(days=365 * 2),
        help="开始日期 YYYY-MM-DD",
    )
    parser.add_argument(
        "--end",
        type=parse_date,
        default=date.today(),
        help="结束日期 YYYY-MM-DD",
    )
    args = parser.parse_args()

    service = OverviewService()
    trade_dates = service.fetch_trade_dates(args.start, args.end)

    print(f"准备导入 {args.start} 至 {args.end} 共 {len(trade_dates)} 个交易日的数据")

    for i, target_date in enumerate(trade_dates, 1):
        try:
            with Session(engine) as session:
                result = service.fetch_daily_overview(target_date, session)
                index_count = len(result.get("indices", []))
                stats = result.get("market_stats", {})
                print(
                    f"[{i}/{len(trade_dates)}] {target_date} - "
                    f"指数 {index_count} 个，涨停 {stats.get('limit_up', 0)}，跌停 {stats.get('limit_down', 0)}，炸板 {stats.get('opened_limit', 0)}"
                )
        except Exception as e:
            print(f"[{i}/{len(trade_dates)}] {target_date} - 失败: {e}")

    print("历史数据导入完成")


if __name__ == "__main__":
    main()
