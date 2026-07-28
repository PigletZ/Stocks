#!/usr/bin/env python3
"""回填历史涨停明细与龙虎榜数据（limit_list_d / top_list）。

用法：
    cd /kimi/projects/Stocks/backend
    source venv/bin/activate
    python scripts/import_limit_history.py [--start 20240102] [--end 20260724] [--sleep 0.35]

已落库的交易日自动跳过，可中断后重跑续传。
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select
from app.database import engine
from app.models import LimitUpDaily
from app.services.overview_service import OverviewService
from app.services.review_service import ReviewService


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="20240102")
    parser.add_argument("--end", default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument("--sleep", type=float, default=0.35)
    args = parser.parse_args()

    start = datetime.strptime(args.start, "%Y%m%d").date()
    end = datetime.strptime(args.end, "%Y%m%d").date()

    overview = OverviewService()
    review = ReviewService()
    trade_dates = overview.fetch_trade_dates(start, end)
    print(f"共 {len(trade_dates)} 个交易日待处理（{start} ~ {end}）")

    done = skipped = failed = 0
    with Session(engine) as session:
        for i, d in enumerate(trade_dates, 1):
            exists = session.exec(
                select(LimitUpDaily.id).where(LimitUpDaily.trade_date == d).limit(1)
            ).first()
            if exists:
                skipped += 1
                continue
            try:
                n1 = review.sync_limit_daily(d, session)
                n2 = review.sync_dragon_tiger_daily(d, session)
                done += 1
                if done % 20 == 0 or i == len(trade_dates):
                    print(f"[{i}/{len(trade_dates)}] {d} 涨停明细 {n1} 条，龙虎榜 {n2} 条（已完成 {done}，跳过 {skipped}）")
            except Exception as e:
                failed += 1
                print(f"[{i}/{len(trade_dates)}] {d} 失败: {e}")
            time.sleep(args.sleep)

    print(f"回填完成：新增 {done} 天，跳过 {skipped} 天，失败 {failed} 天")


if __name__ == "__main__":
    main()
