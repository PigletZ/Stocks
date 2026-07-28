"""为已有数据库新增涨停复盘相关表（limit_up_daily / dragon_tiger_daily）。"""

from sqlmodel import SQLModel, create_engine

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.models import LimitUpDaily, DragonTigerDaily


def main():
    engine = create_engine(settings.database_url)
    SQLModel.metadata.create_all(
        engine,
        tables=[LimitUpDaily.__table__, DragonTigerDaily.__table__],
    )
    print("Review tables (limit_up_daily, dragon_tiger_daily) created.")


if __name__ == "__main__":
    main()
