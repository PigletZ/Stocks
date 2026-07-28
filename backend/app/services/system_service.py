"""系统监控服务：缓存表数据新鲜度、定时任务日志健康度、数据库体积。"""

import logging
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import func
from sqlmodel import Session, select

from ..config import settings
from ..models import (
    Bar,
    DragonTigerDaily,
    FinHighlight,
    IndexDaily,
    LimitUpDaily,
    MarketDailyStat,
    SectorDaily,
    StockDailyQuote,
)


logger = logging.getLogger(__name__)

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"

# 定时任务清单（与系统 crontab 对应）
CRON_JOBS = [
    {"name": "日概览+涨停/龙虎榜落库", "log": "import_daily.log", "schedule": "工作日 16:00", "max_age_days": 3},
    {"name": "策略行情快照同步", "log": "sync_quotes.log", "schedule": "工作日 16:20", "max_age_days": 3},
    {"name": "主板 K 线同步", "log": "sync_bars.log", "schedule": "工作日 16:40", "max_age_days": 3},
    {"name": "财务数据同步", "log": "sync_fin.log", "schedule": "每日 19:00", "max_age_days": 2},
]

# 缓存表清单：(标签, 模型, 日期列名, 容差天数)
CACHE_TABLES = [
    ("市场统计", MarketDailyStat, "stat_date", 3),
    ("指数日线", IndexDaily, "trade_date", 3),
    ("板块日线", SectorDaily, "trade_date", 3),
    ("个股行情快照", StockDailyQuote, "trade_date", 3),
    ("涨停明细", LimitUpDaily, "trade_date", 3),
    ("龙虎榜", DragonTigerDaily, "trade_date", 3),
    ("财务亮点榜", FinHighlight, "stat_date", 5),
    ("K线（主板）", Bar, "timestamp", 5),
]


class SystemService:
    """系统状态监控"""

    def get_status(self, session: Session) -> dict:
        return {
            "generated_at": datetime.now().isoformat(),
            "database": self._db_info(),
            "tables": self._table_freshness(session),
            "cron_jobs": self._cron_health(),
        }

    # ==================== 数据库 ====================

    def _db_info(self) -> dict:
        url = settings.database_url
        path = url.replace("sqlite:///", "") if url.startswith("sqlite") else None
        if path:
            full = Path(path)
            if not full.is_absolute():
                full = Path.cwd() / full
            if full.exists():
                size = full.stat().st_size
                return {
                    "path": str(full),
                    "size_bytes": size,
                    "size_mb": round(size / 1024 / 1024, 1),
                }
        return {"path": path, "size_bytes": None, "size_mb": None}

    # ==================== 缓存表新鲜度 ====================

    def _table_freshness(self, session: Session) -> list:
        result = []
        today = date.today()
        for label, model, date_col, tolerance in CACHE_TABLES:
            col = getattr(model, date_col)
            row = session.exec(select(func.max(col), func.count()).select_from(model)).first()
            max_val, count = row if row else (None, 0)
            if max_val is None:
                result.append({"label": label, "table": model.__tablename__, "max_date": None, "rows": 0, "status": "empty"})
                continue
            max_date = max_val.date() if isinstance(max_val, datetime) else max_val
            age = (today - max_date).days
            status = "ok" if age <= tolerance else "stale"
            result.append({
                "label": label,
                "table": model.__tablename__,
                "max_date": max_date.isoformat(),
                "rows": count,
                "age_days": age,
                "status": status,
            })
        return result

    # ==================== 定时任务日志 ====================

    def _cron_health(self) -> list:
        result = []
        now = datetime.now()
        for job in CRON_JOBS:
            log_path = LOG_DIR / job["log"]
            info = {
                "name": job["name"],
                "schedule": job["schedule"],
                "log": job["log"],
                "last_run": None,
                "age_hours": None,
                "status": "missing",
                "last_lines": [],
                "error": None,
            }
            if log_path.exists():
                mtime = datetime.fromtimestamp(log_path.stat().st_mtime)
                age_hours = round((now - mtime).total_seconds() / 3600, 1)
                info["last_run"] = mtime.isoformat()
                info["age_hours"] = age_hours
                tail = self._tail(log_path, 30)
                info["last_lines"] = tail[-5:]
                err = self._find_error(tail)
                info["error"] = err
                if age_hours > job["max_age_days"] * 24:
                    info["status"] = "stale"
                elif err:
                    info["status"] = "error"
                else:
                    info["status"] = "ok"
            result.append(info)
        return result

    @staticmethod
    def _tail(path: Path, n: int) -> list:
        try:
            with open(path, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - 8192))
                text = f.read().decode("utf-8", errors="replace")
            return [line for line in text.strip().splitlines() if line.strip()][-n:]
        except Exception as e:
            logger.warning("读取日志失败 %s: %s", path, e)
            return []

    @staticmethod
    def _find_error(lines: list) -> Optional[str]:
        for line in reversed(lines):
            if re.search(r"Traceback|\bERROR\b|失败", line):
                return line[:200]
        return None
