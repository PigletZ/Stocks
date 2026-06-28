#!/usr/bin/env python3
"""导入指定日期的板块排行数据到数据库。

用法：
    cd /kimi/projects/Stocks/backend
    source venv/bin/activate
    python scripts/import_sectors_daily.py --date 2026-06-23

参数：
    --date  日期，格式 YYYY-MM-DD（默认今天）
    --type  类型：all / industry / concept（默认 all）
"""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session
from app.database import engine
from app.services.overview_service import OverviewService


def parse_date(s: str) -> date:
    return date.fromisoformat(s)


def main():
    parser = argparse.ArgumentParser(description="导入板块排行日数据")
    parser.add_argument(
        "--date",
        type=parse_date,
        default=date.today(),
        help="日期 YYYY-MM-DD",
    )
    parser.add_argument(
        "--type",
        type=str,
        default="all",
        choices=["all", "industry", "concept"],
        help="板块类型",
    )
    args = parser.parse_args()

    service = OverviewService()
    types_to_sync = []
    if args.type in ("all", "industry"):
        types_to_sync.append("industry")
    if args.type in ("all", "concept"):
        types_to_sync.append("concept")

    with Session(engine) as session:
        for st in types_to_sync:
            count = service.sync_sector_ranking_for_date(args.date, st, session=session)
            print(f"{args.date} {st}: 同步 {count} 条板块数据")

    print("板块数据导入完成")


if __name__ == "__main__":
    main()
