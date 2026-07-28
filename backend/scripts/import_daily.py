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
from datetime import date, timedelta
from pathlib import Path

# 将 backend 目录加入 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select
from app.database import engine
from app.models import LimitUpDaily, SectorDaily
from app.services.overview_service import OverviewService
from app.services.review_service import ReviewService


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

        # 补漏近日市场统计（limit_list_d 发布较晚，16:00 跑时当天数据未就绪不缓存）
        service.fetch_market_history(target_date - timedelta(days=7), target_date, session)

        # 板块排行：同步近日缺失的交易日（ths_daily 发布较晚，当天可能为 0）
        print(f"开始同步板块排行数据...")
        recent_dates = service.fetch_trade_dates(target_date - timedelta(days=10), target_date)
        for d in recent_dates[-3:]:
            for st in ("industry", "concept"):
                exists = session.exec(
                    select(SectorDaily.id)
                    .where(SectorDaily.trade_date == d)
                    .where(SectorDaily.sector_type == st)
                    .limit(1)
                ).first()
                if exists:
                    continue
                count = service.sync_sector_ranking_for_date(d, st, session=session)
                print(f"  {d} {st} 板块 {count} 条")

        # 涨停明细与龙虎榜：同步近日缺失的交易日（当天数据未发布时返回 0，次日补漏）
        print(f"开始同步涨停明细与龙虎榜数据...")
        review = ReviewService()
        recent_dates = service.fetch_trade_dates(target_date - timedelta(days=10), target_date)
        for d in recent_dates[-3:]:
            exists = session.exec(
                select(LimitUpDaily.id).where(LimitUpDaily.trade_date == d).limit(1)
            ).first()
            if exists:
                continue
            limit_count = review.sync_limit_daily(d, session)
            dragon_count = review.sync_dragon_tiger_daily(d, session)
            print(f"  {d}: 涨停明细 {limit_count} 条，龙虎榜 {dragon_count} 条")


if __name__ == "__main__":
    main()
