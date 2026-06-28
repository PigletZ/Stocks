#!/usr/bin/env python3
"""为 IndexDaily 表增加 OHLCV 字段并回填历史数据。

用法：
    cd /kimi/projects/Stocks/backend
    source venv/bin/activate
    python scripts/migrate_add_index_ohlcv.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import date
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, select

from app.database import engine
from app.models import IndexDaily
from app.services.overview_service import OverviewService


def ensure_columns():
    """如果 IndexDaily 表缺少 OHLCV 列，则添加。"""
    columns = [c["name"] for c in inspect(engine).get_columns("indexdaily")]
    required = ["open", "high", "low", "volume", "amount"]
    missing = [c for c in required if c not in columns]
    if not missing:
        print("IndexDaily 表已包含所有 OHLCV 字段，无需添加列")
        return

    with engine.connect() as conn:
        for col in missing:
            try:
                conn.execute(text(f"ALTER TABLE indexdaily ADD COLUMN {col} REAL DEFAULT 0.0"))
                print(f"已添加列: {col}")
            except OperationalError as e:
                print(f"添加列 {col} 失败或已存在: {e}")
        conn.commit()


def backfill_ohlcv():
    """回填已有 IndexDaily 记录中缺失的 OHLCV 数据。"""
    service = OverviewService()
    with Session(engine) as session:
        # 查询所有 close 已有但 open 为 0 或 NULL 的记录
        rows = session.exec(
            select(IndexDaily).where((IndexDaily.open == 0) | (IndexDaily.open == None))
        ).all()
        if not rows:
            print("没有需要回填的 IndexDaily 记录")
            return

        print(f"需要回填 {len(rows)} 条 IndexDaily 记录")
        for i, row in enumerate(rows, 1):
            try:
                data = service.fetch_index_for_date(row.code, row.name, row.trade_date)
                if not data:
                    print(f"[{i}/{len(rows)}] {row.code} {row.trade_date} - 无法获取数据")
                    continue
                row.open = data["open"]
                row.high = data["high"]
                row.low = data["low"]
                row.volume = data["volume"]
                row.amount = data["amount"]
                # 同时刷新 close/change/change_pct，确保一致性
                row.close = data["price"]
                row.change = data["change"]
                row.change_pct = data["change_pct"]
                session.add(row)
                if i % 50 == 0:
                    session.commit()
                    print(f"[{i}/{len(rows)}] 已提交一批")
            except Exception as e:
                print(f"[{i}/{len(rows)}] {row.code} {row.trade_date} - 失败: {e}")
        session.commit()
        print("回填完成")


def main():
    ensure_columns()
    backfill_ohlcv()


if __name__ == "__main__":
    main()
