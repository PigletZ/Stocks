"""为已有数据库新增复盘日志相关表（review_note / trade_journal）。"""

from sqlmodel import SQLModel, create_engine

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.models import ReviewNote, TradeJournal


def main():
    engine = create_engine(settings.database_url)
    SQLModel.metadata.create_all(
        engine,
        tables=[ReviewNote.__table__, TradeJournal.__table__],
    )
    print("Journal tables (review_note, trade_journal) created.")


if __name__ == "__main__":
    main()
