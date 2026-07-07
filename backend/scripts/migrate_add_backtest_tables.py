"""为已有数据库新增回测相关表。"""

from sqlmodel import SQLModel, create_engine

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.models import BacktestRun, BacktestTrade


def main():
    engine = create_engine(settings.database_url)
    SQLModel.metadata.create_all(
        engine,
        tables=[BacktestRun.__table__, BacktestTrade.__table__],
    )
    print("Backtest tables created.")


if __name__ == "__main__":
    main()
