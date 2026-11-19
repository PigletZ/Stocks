"""识别已知同步脚本的实际 cron 计划；不把日志时间当成执行结果。"""
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .job_monitor import process_alive
from .runtime_state import RuntimeStore, redact

JOBS = [
    {"key": "daily", "name": "市场与复盘数据", "impact": "概览、复盘、板块", "log": "import_daily.log"},
    {"key": "quotes", "name": "个股行情快照", "impact": "个股表现、复盘验证", "log": "sync_quotes.log"},
    {"key": "bars", "name": "主板 K 线", "impact": "个股历史走势", "log": "sync_bars.log"},
    {"key": "financial", "name": "财报校验与亮点榜", "impact": "财务分析", "log": "sync_fin.log"},
]


def _values(expression, low, high):
    result = set()
    for part in expression.split(","):
        base, _, step = part.partition("/")
        step = int(step) if step else 1
        if step <= 0:
            raise ValueError("invalid cron step")
        if base == "*":
            first, last = low, high
        elif "-" in base:
            first, last = map(int, base.split("-", 1))
        else:
            first = last = int(base)
        if first < low or last > high or first > last:
            raise ValueError("invalid cron range")
        result.update(range(first, last + 1, step))
    return result


def schedule_times(expression, now, zone):
    try:
        parts = expression.split()
        minute, hour, dom, month, dow = [_values(value, *bounds) for value, bounds in zip(
            parts, [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)])]
        if len(parts) != 5:
            return None, None
        dow = {value % 7 for value in dow}
        local = now.astimezone(zone)
        previous, upcoming = None, None
        for offset in range(-370, 371):
            day = local.date() + timedelta(days=offset)
            day_match, week_match = day.day in dom, day.isoweekday() % 7 in dow
            matches = (day_match or week_match) if parts[2] != "*" and parts[4] != "*" else (day_match and week_match)
            if day.month not in month or not matches:
                continue
            for h in sorted(hour):
                for m in sorted(minute):
                    candidate = datetime(day.year, day.month, day.day, h, m, tzinfo=zone)
                    if candidate <= local and (previous is None or candidate > previous):
                        previous = candidate
                    elif candidate > local and (upcoming is None or candidate < upcoming):
                        upcoming = candidate
        return previous, upcoming
    except (ValueError, TypeError):
        return None, None


def discover_schedules(now):
    schedules = {job["key"]: [] for job in JOBS}
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=2)
        if result.returncode != 0:
            return schedules, False
        zone = now.astimezone().tzinfo
        try:
            zone = ZoneInfo(Path("/etc/timezone").read_text().strip())
        except (OSError, ValueError, KeyError):
            pass
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("CRON_TZ="):
                zone = ZoneInfo(line.split("=", 1)[1].strip().strip('"\''))
                continue
            parts = line.split(None, 5)
            if len(parts) != 6:
                continue
            command = parts[5]
            if "scripts/import_daily.py" in command:
                keys = ["daily"]
            elif "scripts/sync_fin_daily.py" in command:
                keys = ["financial"]
            elif "scripts/sync_strategy_data.py" in command:
                keys = ["quotes"] + ([] if "--skip-bars" in command else ["bars"])
            else:
                continue
            expression = " ".join(parts[:5])
            previous, upcoming = schedule_times(expression, now, zone)
            for key in keys:
                schedules[key].append({"expression": expression, "timezone": str(zone),
                                       "previous": previous.isoformat() if previous else None,
                                       "next": upcoming.isoformat() if upcoming else None})
        return schedules, True
    except (OSError, subprocess.SubprocessError, ValueError, KeyError):
        return schedules, False


def job_statuses(now, log_dir, store=None, discovered=None):
    store = store or RuntimeStore()
    schedules, known = discovered if discovered is not None else discover_schedules(now)
    output = []
    for job in JOBS:
        record = store.read(f"job-{job['key']}")
        item = {**job, "schedules": schedules[job["key"]], "schedule_known": known,
                "next_run": min((plan["next"] for plan in schedules[job["key"]] if plan["next"]), default=None),
                "last_run": None, "status": "missing", "message": "尚无结构化执行记录，下一次任务执行后开始记录",
                "log_updated_at": None, "log_excerpt": [], "record": record}
        log = Path(log_dir) / job["log"]
        if log.exists():
            from datetime import timezone
            item["log_updated_at"] = datetime.fromtimestamp(log.stat().st_mtime, timezone.utc).isoformat()
            try:
                with log.open("rb") as handle:
                    handle.seek(0, 2)
                    handle.seek(max(0, handle.tell()-4096))
                    lines = handle.read().decode("utf-8", errors="replace").splitlines()[-8:]
                item["log_excerpt"] = [redact(line)[:300] for line in lines]
                item["status"] = "unverified"
                if any(re.search(r"Traceback|\bERROR\b|失败", line) for line in lines):
                    item["message"] = "旧日志包含失败信息；尚无可核验的本次执行结果"
            except OSError:
                item["message"] = "日志不可读取，执行结果待核验"
        if record:
            item.update(status=record.get("status", "unknown"), last_run=record.get("started_at"), message=redact(record.get("message", "")))
            if item["status"] == "running" and not process_alive(record):
                item.update(status="interrupted", message="进程已退出，但没有完成记录；可能被终止或发生崩溃")
            previous = max((plan["previous"] for plan in schedules[job["key"]] if plan["previous"]), default=None)
            try:
                if (item["status"] in {"success", "skipped"} and previous
                        and datetime.fromisoformat(record["started_at"]) < datetime.fromisoformat(previous)
                        and (now - datetime.fromisoformat(previous)).total_seconds() > 1800):
                    item.update(status="stale", message="最近一次计划时间已过，尚未看到对应的新执行记录")
            except (ValueError, KeyError, TypeError):
                item.update(status="unknown", message="执行记录时间无效，需重新核验")
        output.append(item)
    return output
