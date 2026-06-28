#!/usr/bin/env python3
"""导入今日日概览数据到数据库。

用法：
    cd /kimi/projects/Stocks/backend
    source venv/bin/activate
    python scripts/import_daily.py

建议通过系统 crontab 每日 16:00 执行：
    0 16 * * * cd /kimi/projects/Stocks/backend && source venv/bin/activate && python scripts/import_daily.py
"""

import sys
from datetime import date
from pathlib import Path

# 将 backend 目录加入 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session
from app.database import engine
from app.services.overview_service import OverviewService


def main():
    target_date = date.today()
    service = OverviewService()

    # 仅导入交易日
    trade_dates = service.fetch_trade_dates(target_date, target_date)
    if not trade_dates:
        print(f"{target_date} 非交易日，跳过导入")
        return

    with Session(engine) as session:
        print(f"开始导入 {target_date} 的日概览数据...")
        result = service.fetch_daily_overview(target_date, session)
        index_count = len(result.get("indices", []))
        stats = result.get("market_stats", {})
        print(f"完成：{index_count} 个指数，涨停 {stats.get('limit_up', 0)} 家，跌停 {stats.get('limit_down', 0)} 家，炸板 {stats.get('opened_limit', 0)} 家")

        print(f"开始导入 {target_date} 的板块排行数据...")
        for st in ("industry", "concept"):
            count = service.sync_sector_ranking_for_date(target_date, st, session=session)
            print(f"完成：{st} 板块 {count} 条")


if __name__ == "__main__":
    main()
