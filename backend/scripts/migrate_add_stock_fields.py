#!/usr/bin/env python3
"""为 stock 表添加 industry、list_date、updated_at 字段。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, text
from app.database import engine


def main():
    inspector = inspect(engine)
    columns = [col["name"] for col in inspector.get_columns("stock")]

    with engine.connect() as conn:
        if "industry" not in columns:
            conn.execute(text("ALTER TABLE stock ADD COLUMN industry VARCHAR"))
            print("Added column: industry")
        if "list_date" not in columns:
            conn.execute(text("ALTER TABLE stock ADD COLUMN list_date DATE"))
            print("Added column: list_date")
        if "updated_at" not in columns:
            conn.execute(text("ALTER TABLE stock ADD COLUMN updated_at DATETIME"))
            print("Added column: updated_at")
        conn.commit()


if __name__ == "__main__":
    main()
