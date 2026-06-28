#!/usr/bin/env python3
"""创建 stockdailyquote 表。若表已存在则先删除重建，确保列定义与模型一致。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.database import engine
from app.models import StockDailyQuote


def main():
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS stockdailyquote"))
        conn.commit()
    StockDailyQuote.metadata.create_all(engine)
    print("Created table: stockdailyquote")


if __name__ == "__main__":
    main()
