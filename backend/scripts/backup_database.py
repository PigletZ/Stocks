"""生成 SQLite 在线一致性备份并校验；不会直接复制正在写入的数据库文件。"""
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.engine import make_url
from app.config import settings
from app.services.job_monitor import tracked_job, record_progress
from app.services.runtime_state import BACKEND_DIR, RuntimeStore, utc_now


def backup_database(database_url=None, directory=None, store=None):
    url = make_url(database_url or settings.database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise RuntimeError("备份脚本仅支持文件型 SQLite 数据库")
    source_path = Path(url.database).resolve()
    if not source_path.is_file():
        raise RuntimeError("源数据库文件不存在")
    target_dir = Path(directory or settings.backup_dir or BACKEND_DIR / "backups").resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    created = utc_now()
    filename = f"stocks-{created.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}.sqlite3"
    temporary = target_dir / (filename + ".part")
    target = target_dir / filename
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        with closing(sqlite3.connect(source_path.as_uri()+"?mode=ro", uri=True, timeout=30)) as source:
            with closing(sqlite3.connect(temporary)) as destination:
                source.backup(destination, pages=256, sleep=.05)
                if destination.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                    raise RuntimeError("备份未通过 SQLite quick_check")
        os.replace(temporary, target)
        manifest = {"filename": filename, "created_at": created.isoformat(), "verified_at": utc_now().isoformat(),
                    "size_bytes": target.stat().st_size, "check": "ok"}
        (store or RuntimeStore()).write("backup", manifest)
        return manifest
    finally:
        if temporary.exists():
            temporary.unlink()


@tracked_job("backup")
def main():
    manifest = backup_database()
    record_progress(succeeded=1, unit="备份", message="SQLite 备份已生成并通过校验")
    print("已生成并校验备份：" + manifest["filename"])


if __name__ == "__main__":
    main()
