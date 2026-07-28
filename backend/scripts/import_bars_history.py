#!/usr/bin/env python3
"""回填主板历史 K 线（按交易日批量拉 daily，一次请求覆盖全市场）。

用法：
    cd /kimi/projects/Stocks/backend
    source venv/bin/activate
    python scripts/import_bars_history.py [--years 2] [--sleep 0.3]

已回填的交易日（行数达标）自动跳过，可中断后重跑续传。
"""

import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func
from sqlmodel import Session, select

from app.database import engine
from app.models import Bar, MarketDailyStat
from app.services.tushare_stock_service import TushareStockService


def is_main_board(code: str) -> bool:
    return code.startswith(("60", "00"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=float, default=2, help="回填年数")
    parser.add_argument("--sleep", type=float, default=0.3)
    args = parser.parse_args()

    start = datetime.now().date() - timedelta(days=int(args.years * 365))

    service = TushareStockService()
    pro = service._get_tushare_pro()

    with Session(engine) as session:
        dates = session.exec(
            select(MarketDailyStat.stat_date)
            .where(MarketDailyStat.stat_date >= start)
            .order_by(MarketDailyStat.stat_date)
        ).all()
        print(f"共 {len(dates)} 个交易日待处理（{start} 起）")

        done = skipped = failed = 0
        for i, d in enumerate(dates, 1):
            ts = datetime(d.year, d.month, d.day)
            existing = session.exec(
                select(func.count()).select_from(Bar)
                .where(Bar.timestamp == ts)
                .where(Bar.interval == "1d")
            ).one()
            if existing > 2000:
                skipped += 1
                continue
            try:
                df = pro.daily(trade_date=d.strftime("%Y%m%d"))
                if df is None or df.empty:
                    skipped += 1
                    continue
                df["code"] = df["ts_code"].astype(str).str.split(".").str[0]
                df = df[df["code"].apply(is_main_board)]
                # 清理当天已有但可能不完整的行，整体重写
                if existing:
                    session.exec(
                        Bar.__table__.delete()
                        .where(Bar.timestamp == ts)
                        .where(Bar.interval == "1d")
                    )
                bars = [
                    Bar(
                        stock_code=r["code"],
                        timestamp=ts,
                        interval="1d",
                        open=float(r["open"]),
                        high=float(r["high"]),
                        low=float(r["low"]),
                        close=float(r["close"]),
                        volume=float(r["vol"]) * 100,  # 手 → 股
                        adjusted=False,
                    )
                    for r in df.to_dict("records")
                ]
                session.add_all(bars)
                session.commit()
                done += 1
                if done % 20 == 0 or i == len(dates):
                    print(f"[{i}/{len(dates)}] {d} 写入 {len(bars)} 条（已完成 {done}，跳过 {skipped}）")
            except Exception as e:
                session.rollback()
                failed += 1
                print(f"[{i}/{len(dates)}] {d} 失败: {e}")
            time.sleep(args.sleep)

        print(f"回填完成：新增 {done} 天，跳过 {skipped} 天，失败 {failed} 天")


if __name__ == "__main__":
    main()
