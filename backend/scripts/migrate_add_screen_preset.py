"""为已有数据库新增选股器预设表（screen_preset）。"""

from sqlmodel import SQLModel, create_engine

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.models import ScreenPreset


def main():
    engine = create_engine(settings.database_url)
    SQLModel.metadata.create_all(engine, tables=[ScreenPreset.__table__])
    print("ScreenPreset table created.")


if __name__ == "__main__":
    main()
