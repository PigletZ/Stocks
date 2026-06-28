#!/usr/bin/env python3
"""为 MarketDailyStat 表添加 total_turnover 列。

用法：
    cd /kimi/projects/Stocks/backend
    source venv/bin/activate
    python scripts/migrate_add_total_turnover.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, text
from app.database import engine


def main():
    inspector = inspect(engine)
    columns = [col["name"] for col in inspector.get_columns("marketdailystat")]

    if "total_turnover" in columns:
        print("total_turnover 列已存在，跳过迁移")
        return

    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE marketdailystat ADD COLUMN total_turnover FLOAT DEFAULT 0.0"))
        conn.commit()
    print("已添加 total_turnover 列")


if __name__ == "__main__":
    main()
