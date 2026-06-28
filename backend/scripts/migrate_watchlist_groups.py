#!/usr/bin/env python3
"""创建 watchlistgroup 表，并把 watchlistitem.group_name 迁移为 group_id，最后重建 watchlistitem 表。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, text
from app.database import engine


def main():
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    with engine.connect() as conn:
        if "watchlistgroup" not in tables:
            conn.execute(
                text(
                    """
                    CREATE TABLE watchlistgroup (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name VARCHAR NOT NULL UNIQUE,
                        sort_order INTEGER DEFAULT 0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            print("Created table: watchlistgroup")

        # 迁移已有 group_name 到 watchlistgroup
        if "watchlistitem" in tables:
            columns = [col["name"] for col in inspector.get_columns("watchlistitem")]

            if "group_name" in columns:
                conn.execute(
                    text(
                        """
                        INSERT OR IGNORE INTO watchlistgroup (name, sort_order, created_at)
                        SELECT DISTINCT group_name, 0, CURRENT_TIMESTAMP FROM watchlistitem
                        WHERE group_name IS NOT NULL AND group_name != ''
                        """
                    )
                )
                print("Migrated existing group names to watchlistgroup")

            if "group_id" not in columns:
                conn.execute(text("ALTER TABLE watchlistitem ADD COLUMN group_id INTEGER"))
                print("Added column: watchlistitem.group_id")

            if "group_name" in columns:
                conn.execute(
                    text(
                        """
                        UPDATE watchlistitem
                        SET group_id = (
                            SELECT id FROM watchlistgroup
                            WHERE watchlistgroup.name = watchlistitem.group_name
                        )
                        """
                    )
                )
                # 对未命中的记录兜底到"默认分组"
                result = conn.execute(
                    text(
                        """
                        SELECT id FROM watchlistgroup WHERE name = '默认分组' LIMIT 1
                        """
                    )
                ).fetchone()
                if result is None:
                    conn.execute(
                        text(
                            """
                            INSERT INTO watchlistgroup (name, sort_order, created_at)
                            VALUES ('默认分组', 0, CURRENT_TIMESTAMP)
                            """
                        )
                    )
                    result = conn.execute(
                        text(
                            """
                            SELECT id FROM watchlistgroup WHERE name = '默认分组' LIMIT 1
                            """
                        )
                    ).fetchone()
                default_group_id = result[0]
                conn.execute(
                    text(
                        f"""
                        UPDATE watchlistitem
                        SET group_id = {default_group_id}
                        WHERE group_id IS NULL
                        """
                    )
                )
                print("Migrated watchlistitem.group_id")

            # 重建 watchlistitem 表，移除旧的 group_name 列
            conn.execute(
                text(
                    """
                    CREATE TABLE watchlistitem_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        stock_code VARCHAR NOT NULL,
                        group_id INTEGER,
                        sort_order INTEGER DEFAULT 0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE (stock_code)
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO watchlistitem_new (id, stock_code, group_id, sort_order, created_at)
                    SELECT id, stock_code, group_id, sort_order, created_at FROM watchlistitem
                    """
                )
            )
            conn.execute(text("DROP TABLE watchlistitem"))
            conn.execute(text("ALTER TABLE watchlistitem_new RENAME TO watchlistitem"))
            print("Recreated watchlistitem table without group_name")

        conn.commit()


if __name__ == "__main__":
    main()
