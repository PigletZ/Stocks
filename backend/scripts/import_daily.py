#!/usr/bin/env python3
"""补齐最近三个真实交易日；建议 16:00 首次采集，18:30/20:30 再次补漏。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session
from app.database import engine
from app.services.daily_sync import DailySyncService
from app.services.job_monitor import tracked_job
from app.services.review_workbench import today_shanghai


@tracked_job("daily")
def main():
    with Session(engine) as session:
        DailySyncService().sync_recent(today_shanghai(), session)


if __name__ == "__main__":
    main()
