"""为 bar 表新增 timestamp 索引（K线回填与本地回测按日期查询用）。"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.database import engine


def main():
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_bar_timestamp ON bar(timestamp)"))
    print("bar(timestamp) index created.")


if __name__ == "__main__":
    main()
