"""系统管理：本地数据、真实任务结果、诊断及维护状态。GET 不访问 Tushare。"""
import shutil
import subprocess
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, or_
from sqlmodel import select

from ..config import settings
from ..models import (Bar, DragonTigerDaily, FinHighlight, IndexDaily, LimitUpDaily,
                      MarketDailyStat, SectorDaily, Stock, StockDailyQuote)
from .etf_service import EtfService
from .runtime_state import BACKEND_DIR, RuntimeStore, SystemPreferences, get_preferences, utc_now
from .system_diagnostics import SystemDiagnostics
from .system_jobs import job_statuses

SHANGHAI = timezone(timedelta(hours=8))
STARTED_AT = utc_now()
TABLES = [
    ("市场统计", MarketDailyStat, "stat_date", "概览、市场情绪"),
    ("主要指数", IndexDaily, "trade_date", "概览指数走势"),
    ("板块行情", SectorDaily, "trade_date", "方向强弱、板块排行"),
    ("个股行情快照", StockDailyQuote, "trade_date", "个股表现、复盘验证"),
    ("涨跌停明细", LimitUpDaily, "trade_date", "复盘梯队、涨跌停结构"),
    ("龙虎榜", DragonTigerDaily, "trade_date", "龙虎榜复盘"),
    ("财务亮点榜", FinHighlight, "stat_date", "财务亮点；日期仅代表榜单计算日"),
    ("主板 K 线", Bar, "timestamp", "个股历史走势"),
]


def expected_trade_date(dates, now, ready_hour):
    local = now.astimezone(SHANGHAI)
    eligible = [day for day in dates if day < local.date() or (day == local.date() and local.hour >= ready_hour)]
    return max(eligible) if eligible else None


class SystemService:
    def __init__(self, store=None, etf=None, now=None, log_dir=None, discovered=None):
        self.store = store or RuntimeStore()
        self.etf = etf or EtfService()
        self.now = now or utc_now()
        self.log_dir = log_dir or BACKEND_DIR / "logs"
        self.discovered = discovered

    def get_status(self, session):
        preferences = get_preferences(self.store)
        local_day = self.now.astimezone(SHANGHAI).date()
        calendar = self.etf.cached_trade_dates(local_day-timedelta(days=60), local_day)
        expected = expected_trade_date(calendar[0], self.now, preferences.data_ready_hour) if calendar else None
        tables = self._table_freshness(session, expected)
        jobs = job_statuses(self.now, self.log_dir, self.store, self.discovered)
        diagnostics = SystemDiagnostics(self.store).get_report(self.now)
        database, backup = self._db_info(session), self._backup_info()
        alerts = []
        if expected is None:
            alerts.append(self._alert("calendar", "warning", "交易日历尚未确认", "数据的最新记录仍可查看，时效暂不判为正常", "点击“检查数据源”，获取覆盖完整的官方日历"))
        for table in tables:
            if table["status"] in {"empty", "stale", "partial"}:
                alerts.append(self._alert(table["table"], "error" if table["status"] == "empty" else "warning", f"{table['label']}需要关注", table["message"], f"影响：{table['impact']}；检查对应同步任务和数据源"))
        for job in jobs:
            if job["status"] not in {"success", "running", "skipped"}:
                alerts.append(self._alert(f"job-{job['key']}", "error" if job["status"] in {"error", "interrupted"} else "warning", f"{job['name']}：执行结果待处理", job["message"], "展开任务查看执行记录与日志摘要"))
        if diagnostics["status"] != "ok":
            checks = [check for check in diagnostics["checks"] if check.get("status") == "error"]
            detail = "；".join(f"{check['label']}：{check['message']}" for check in checks[:2]) if diagnostics["fresh"] else "尚无最近 10 分钟内的有效诊断结果"
            alerts.append(self._alert("source", "error" if diagnostics["status"] == "error" else "warning", "数据源需要检查", detail or "部分接口未返回可核验的样本", "点击“检查数据源”；单接口可用不代表所有模块均已同步"))
        if database["status"] == "warning":
            alerts.append(self._alert("disk", "warning", "磁盘空间偏低", "磁盘余量低于 2 GB 或 5%", "检查日志和备份占用，保留可恢复的备份"))
        if backup["status"] != "ok":
            alerts.append(self._alert("backup", "warning", "备份状态需要关注", backup["message"], "通过备份脚本生成并校验 SQLite 一致性备份"))
        config = self._configuration()
        if config["preferences_status"] == "error":
            alerts.append(self._alert("preferences", "warning", "常用配置读取失败", "已使用默认值", "核对后重新保存常用配置"))
        alerts.sort(key=lambda item: item["severity"] != "error")
        latest = session.exec(select(func.max(IndexDaily.trade_date))).first()
        return {"generated_at": self.now.isoformat(), "timezone": "Asia/Shanghai",
                "summary": {"status": "error" if any(item["severity"] == "error" for item in alerts) else "warning" if alerts else "ok",
                            "alert_count": len(alerts), "latest_local_date": latest.isoformat() if latest else None,
                            "expected_date": expected.isoformat() if expected else None,
                            "data_ok": sum(item["status"] == "ok" for item in tables), "data_total": len(tables),
                            "data_unknown": sum(item["status"] == "unknown" for item in tables),
                            "jobs_ok": sum(item["status"] in {"success", "skipped"} for item in jobs), "jobs_total": len(jobs)},
                "calendar": {"status": "cached" if calendar else "unknown", "fetched_at": calendar[1].isoformat() if calendar else None,
                             "ready_hour": preferences.data_ready_hour, "today_open": local_day in calendar[0] if calendar else None},
                "alerts": alerts, "database": database, "tables": tables, "cron_jobs": jobs,
                "diagnostics": diagnostics, "cache": self._cache_info(), "backup": backup,
                "configuration": config, "preferences": preferences.model_dump(),
                "runtime": {"started_at": STARTED_AT.isoformat(), "version": self._version(), "status": "ok"}}

    @staticmethod
    def _alert(key, severity, title, detail, action):
        return dict(key=key, severity=severity, title=title, detail=detail, action=action)

    @staticmethod
    def _version():
        try:
            result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=BACKEND_DIR, capture_output=True, text=True, timeout=1)
            return result.stdout.strip() if result.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            return None

    @staticmethod
    def _db_info(session):
        path = session.get_bind().url.database
        info = {"name": None, "size_bytes": None, "size_mb": None, "free_bytes": None, "free_percent": None, "status": "unknown"}
        if not path or path == ":memory:":
            return info
        try:
            path = Path(path).resolve()
            size, usage = path.stat().st_size, shutil.disk_usage(path.parent)
            return {"name": path.name, "size_bytes": size, "size_mb": round(size/1024**2, 1),
                    "free_bytes": usage.free, "free_percent": round(usage.free/usage.total*100, 1),
                    "status": "warning" if usage.free < 2*1024**3 or usage.free/usage.total < .05 else "ok"}
        except OSError:
            return info

    def _table_freshness(self, session, expected):
        output = []
        for label, model, name, impact in TABLES:
            column = getattr(model, name)
            scope = [Bar.interval == "1d", or_(Bar.stock_code.like("60%"), Bar.stock_code.like("00%"))] if model is Bar else []
            latest = session.exec(select(func.max(column)).where(*scope)).first()
            latest_day = latest.date() if isinstance(latest, datetime) else latest
            check_day = expected or latest_day
            item = {"label": label, "table": model.__tablename__, "impact": impact,
                    "max_date": latest_day.isoformat() if latest_day else None,
                    "expected_date": expected.isoformat() if expected else None,
                    "checked_date": check_day.isoformat() if check_day else None, "rows": 0,
                    "reference_rows": None, "coverage_pct": None, "coverage_note": "",
                    "status": "unknown", "message": "交易日历未确认，数据时效待核验"}
            if latest_day is None:
                item.update(status="empty", message="本地没有可用记录，需核验首次同步或接口是否应返回数据")
                output.append(item)
                continue
            if model is Bar:
                start = datetime.combine(check_day, time.min)
                filters = scope + [column >= start, column < start+timedelta(days=1)]
            else:
                filters = [column == check_day]
            count = session.exec(select(func.count()).select_from(model).where(*filters)).one()
            item["rows"] = count
            stat = session.exec(select(MarketDailyStat).where(MarketDailyStat.stat_date == check_day)).first()
            if model is IndexDaily:
                from .overview_service import OverviewService
                reference = len(OverviewService.INDEX_CODES)
                valid = session.exec(select(func.count(func.distinct(IndexDaily.code))).where(*filters, IndexDaily.code.in_(OverviewService.INDEX_CODES))).one()
                item.update(reference_rows=reference, coverage_pct=round(valid/reference*100, 1), coverage_note="固定的 5 个主要指数")
            elif model in (StockDailyQuote, Bar):
                pool = [or_(Stock.list_date.is_(None), Stock.list_date <= check_day)]
                if model is Bar:
                    pool.append(or_(Stock.code.like("60%"), Stock.code.like("00%")))
                reference = session.exec(select(func.count()).select_from(Stock).where(*pool)).one()
                valid = session.exec(select(func.count()).select_from(model).where(*filters, model.close > 0)).one()
                if reference:
                    item.update(reference_rows=reference, coverage_pct=round(min(valid/reference, 1)*100, 1), coverage_note="相对本地股票池；停牌等会影响覆盖，低于 95% 提示核验")
            elif model is SectorDaily:
                previous = session.exec(select(func.max(column)).where(column < check_day)).first()
                if previous:
                    reference = session.exec(select(func.count()).select_from(model).where(column == previous)).one()
                    item.update(reference_rows=reference, coverage_pct=round(min(count/reference, 1)*100, 1) if reference else None, coverage_note=f"参考上一有数据日期 {previous}，低于 85% 提示核验")
            elif model is LimitUpDaily and stat and stat.total > 0:
                reference = stat.limit_up + stat.limit_down + stat.opened_limit
                if reference:
                    item.update(reference_rows=reference, coverage_pct=round(min(count/reference, 1)*100, 1), coverage_note="与同日市场涨停、跌停及炸板统计比对")
            if expected and latest_day < expected:
                item.update(status="stale", message=f"本次应有 {expected}，本地最新为 {latest_day}")
            elif expected and count == 0:
                item.update(status="empty", message=f"{expected} 没有记录；可能未发布或无需记录，需核验任务和接口")
            elif latest_day > self.now.astimezone(SHANGHAI).date():
                item.update(status="partial", message="存在未来日期记录，需核对同步参数")
            else:
                quality_issue = None
                if model is MarketDailyStat and (not stat or stat.total <= 0 or stat.up+stat.down+stat.flat != stat.total or stat.total_turnover <= 0):
                    quality_issue = "涨跌家数、样本数或成交额不完整"
                threshold = 85 if model is SectorDaily else 100 if model in (IndexDaily, LimitUpDaily) else 95
                if item["coverage_pct"] is not None and item["coverage_pct"] < threshold:
                    quality_issue = f"该日覆盖约 {item['coverage_pct']}%，低于核验门槛"
                if model is SectorDaily:
                    kinds = set(session.exec(select(SectorDaily.sector_type).where(*filters).distinct()).all())
                    if not {"industry", "concept"}.issubset(kinds):
                        quality_issue = "行业或概念板块缺失"
                if quality_issue:
                    item.update(status="partial", message=quality_issue)
                elif expected:
                    item.update(status="ok", message="核验日期与可量化的覆盖检查通过" if item["reference_rows"] else "已有当日记录；该数据集尚无完整覆盖基准")
            output.append(item)
        return output

    def _cache_info(self):
        directory = self.etf._frame_cache.directory
        try:
            files = list(directory.glob("*.json"))
            daily = sorted(path for path in files if path.name.startswith("daily-"))
            newest = daily[-1] if daily else None
            day = datetime.strptime(newest.stem[6:], "%Y%m%d").date().isoformat() if newest else None
            return {"status": "cached" if daily else "empty", "snapshots": len(daily), "latest_date": day, "size_bytes": sum(path.stat().st_size for path in files),
                    "basic_available": (directory / "basic.json").exists(), "note": "文件数量不代表所有涨幅窗口都有可用基准；实际回退以 ETF 页面校验结果为准"}
        except (OSError, ValueError):
            return {"status": "unknown", "snapshots": 0, "latest_date": None, "size_bytes": 0, "basic_available": False, "note": "缓存目录无法完整读取"}

    def _backup_info(self):
        manifest = self.store.read("backup")
        result = {"status": "unknown", "created_at": None, "verified_at": None, "size_bytes": None, "filename": None, "message": "尚无受管理且经过校验的备份记录；其他目录的备份未纳入此状态"}
        if not manifest:
            return result
        try:
            filename = manifest["filename"]
            if Path(filename).name != filename:
                return result
            path = Path(settings.backup_dir or BACKEND_DIR / "backups") / filename
            if path.stat().st_size != manifest["size_bytes"] or manifest.get("check") != "ok":
                result.update(status="warning", message="备份文件缺失、大小变化或未通过校验")
                return result
            age = (self.now-datetime.fromisoformat(manifest["created_at"])).total_seconds()
            result.update({key: manifest.get(key) for key in ("created_at", "verified_at", "size_bytes", "filename")})
            result.update(status="ok" if 0 <= age <= 48*3600 else "warning", message="最近备份已通过 SQLite quick_check；当前未自动推断备份计划" if age <= 48*3600 else "最近备份已超过 48 小时，建议更新")
            return result
        except (OSError, KeyError, TypeError, ValueError):
            result.update(status="warning", message="备份记录或文件无法核验")
            return result

    def _configuration(self):
        payload = self.store.read("preferences")
        valid = True
        try:
            if payload:
                SystemPreferences.model_validate(payload["values"])
            elif self.store.path("preferences").exists():
                valid = False
        except (ValueError, KeyError, TypeError):
            valid = False
        return {"tushare_configured": bool(settings.tushare_token), "authentication_configured": bool(settings.auth_username and settings.auth_password and settings.auth_secret),
                "public_host_configured": bool(settings.public_host), "preferences_status": "ok" if valid else "error", "preferences_saved_at": payload.get("updated_at") if payload else None,
                "note": "凭据保留在服务端环境配置中；已配置不代表接口权限已验证"}
