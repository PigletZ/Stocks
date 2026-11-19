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
from app.models import LimitUpDaily, DragonTigerDaily, SectorDaily, MarketDailyStat
from app.services.overview_service import OverviewService
from app.services.review_service import ReviewService
from app.services.job_monitor import tracked_job, record_progress


@tracked_job("daily")
def main():
    target_date = date.today()
    service = OverviewService()

    # 仅导入交易日
    trade_dates = service.fetch_trade_dates(target_date, target_date)
    if not trade_dates:
        record_progress(skipped=1, message="官方交易日历确认今日休市", unit="数据集", confirmed_skip=True)
        print(f"{target_date} 非交易日，跳过导入")
        return

    with Session(engine) as session:
        print(f"开始导入 {target_date} 的日概览数据...")
        result = service.fetch_daily_overview(target_date, session)
        index_count = len(result.get("indices", []))
        stats = result.get("market_stats", {})
        if index_count == len(service.INDEX_CODES):
            record_progress(succeeded=1, written_rows=index_count, unit="数据集")
        else:
            record_progress(failed=1, message=f"指数仅取得 {index_count}/{len(service.INDEX_CODES)} 个", unit="数据集")
        stat = session.exec(select(MarketDailyStat).where(MarketDailyStat.stat_date == target_date)).first()
        if stat and stat.total > 0 and stat.up + stat.down + stat.flat == stat.total:
            record_progress(succeeded=1, written_rows=1, unit="数据集")
        else:
            record_progress(failed=1, message="当日市场统计未就绪，未确认同步成功", unit="数据集")
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
                    record_progress(skipped=1, unit="数据集")
                    continue
                count = service.sync_sector_ranking_for_date(d, st, session=session)
                record_progress(succeeded=int(count > 0), failed=int(count == 0), written_rows=count,
                                message=f"{d} {st} 板块 {'完成' if count else '无数据，待核验'}", unit="数据集")
                print(f"  {d} {st} 板块 {count} 条")

        # 涨停明细与龙虎榜：同步近日缺失的交易日（当天数据未发布时返回 0，次日补漏）
        print(f"开始同步涨停明细与龙虎榜数据...")
        review = ReviewService()
        recent_dates = service.fetch_trade_dates(target_date - timedelta(days=10), target_date)
        for d in recent_dates[-3:]:
            for model, sync in ((LimitUpDaily, review.sync_limit_daily), (DragonTigerDaily, review.sync_dragon_tiger_daily)):
                exists = session.exec(select(model.id).where(model.trade_date == d).limit(1)).first()
                if exists:
                    record_progress(skipped=1, unit="数据集")
                    continue
                count = sync(d, session)
                record_progress(succeeded=int(count > 0), failed=int(count == 0), written_rows=count,
                                message=f"{d} {model.__tablename__} {'完成' if count else '无数据，待核验'}", unit="数据集")
                print(f"  {d}: {model.__tablename__} {count} 条")


if __name__ == "__main__":
    main()
