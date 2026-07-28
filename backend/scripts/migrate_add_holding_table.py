"""为已有数据库新增手动持仓表（holding）。"""

from sqlmodel import SQLModel, create_engine

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.models import Holding


def main():
    engine = create_engine(settings.database_url)
    SQLModel.metadata.create_all(engine, tables=[Holding.__table__])
    print("Holding table created.")


if __name__ == "__main__":
    main()
