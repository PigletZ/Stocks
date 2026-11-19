"""按用户请求检查 Tushare；常规状态刷新不触发远程调用。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Lock
from time import monotonic

from .etf_service import EtfService
from .runtime_state import RuntimeStore, redact, utc_now
from .tushare_client import TushareClient, TushareError
from ..config import settings

_lock = Lock()


class DiagnosticBusy(RuntimeError):
    pass


class SystemDiagnostics:
    def __init__(self, store=None):
        self.store = store or RuntimeStore()

    def get_report(self, now=None):
        report = self.store.read("diagnostics")
        if not report:
            return {"status": "unknown", "checked_at": None, "fresh": False, "checks": []}
        try:
            age = ((now or utc_now()) - datetime.fromisoformat(report["checked_at"])).total_seconds()
            report["fresh"] = 0 <= age <= 600
            report["status"] = ("error" if any(check["status"] == "error" for check in report["checks"]) else
                                "ok" if all(check["status"] == "ok" for check in report["checks"]) and report["checks"] else "unknown") if report["fresh"] else "unknown"
            return report
        except (KeyError, TypeError, ValueError):
            return {"status": "unknown", "checked_at": None, "fresh": False, "checks": []}

    def run(self):
        if not _lock.acquire(blocking=False):
            raise DiagnosticBusy("数据源检查正在进行，请稍后刷新结果")
        try:
            previous = self.get_report()
            if previous["checked_at"] and (utc_now()-datetime.fromisoformat(previous["checked_at"])).total_seconds() < 30:
                return previous
            today = utc_now().astimezone(timezone(timedelta(hours=8))).date()
            start = today - timedelta(days=45)
            params = {"start_date": start.strftime("%Y%m%d"), "end_date": today.strftime("%Y%m%d"), "limit": 1}
            tasks = [
                ("calendar", "交易日历", "trade_cal", {}, "cal_date"),
                ("stocks", "股票日线", "daily", {**params, "ts_code": "600519.SH", "fields": "ts_code,trade_date,close"}, "trade_date"),
                ("indices", "指数日线", "index_daily", {**params, "ts_code": "000001.SH", "fields": "ts_code,trade_date,close"}, "trade_date"),
                ("etf", "ETF 日线", "fund_daily", {**params, "ts_code": "510300.SH", "fields": "ts_code,trade_date,close"}, "trade_date"),
                ("income", "利润表", "income", {"ts_code": "600519.SH", "limit": 1, "fields": "ts_code,end_date"}, "end_date"),
                ("balance", "资产负债表", "balancesheet", {"ts_code": "600519.SH", "limit": 1, "fields": "ts_code,end_date"}, "end_date"),
                ("cashflow", "现金流量表", "cashflow", {"ts_code": "600519.SH", "limit": 1, "fields": "ts_code,end_date"}, "end_date"),
            ]

            def check(task):
                key, label, api, arguments, date_field = task
                started = monotonic()
                result = {"key": key, "label": label, "api": api, "status": "unknown", "kind": None,
                          "message": "", "sample_date": None, "checked_at": utc_now().isoformat()}
                try:
                    if not settings.tushare_token:
                        raise TushareError("Tushare Token 未配置", kind="unconfigured")
                    client = TushareClient(settings.tushare_token)
                    if key == "calendar":
                        service = EtfService()
                        open_dates = []
                        for year in range(start.year, today.year+1):
                            frame = client.trade_cal(exchange="SSE", start_date=f"{year}0101", end_date=f"{year}1231", fields="exchange,cal_date,is_open")
                            frame = service._normalize_calendar(frame, max(start, today.replace(year=year, month=1, day=1)), min(today, today.replace(year=year, month=12, day=31)))
                            service._frame_cache.put(f"calendar-{year}", frame)
                            open_dates.extend(frame.loc[frame["is_open"] == 1, "cal_date"].tolist())
                        result["sample_date"] = max((day for day in open_dates if day <= today.strftime("%Y%m%d")), default=None)
                        result.update(status="ok", message="官方日历已校验并保存，支持休市日判断")
                    else:
                        frame = getattr(client, api)(**arguments)
                        if frame is not None and not frame.empty and date_field in frame:
                            result.update(status="ok", message="接口采样成功；不代表全市场数据已同步齐全", sample_date=str(frame.iloc[0][date_field]))
                        else:
                            result.update(status="unknown", kind="empty", message="接口可达但未返回样本，数据可用性待核验")
                except TushareError as error:
                    result.update(status="error", kind=error.kind, message=redact(error), http_status=error.http_status, code=error.code)
                except Exception:
                    result.update(status="error", kind="protocol", message="返回数据不完整，无法核验")
                result["duration_ms"] = round((monotonic()-started)*1000)
                return result

            with ThreadPoolExecutor(max_workers=4) as pool:
                checks = list(pool.map(check, tasks))
            report = {"checked_at": utc_now().isoformat(), "checks": checks}
            self.store.write("diagnostics", report)
            return self.get_report()
        finally:
            _lock.release()
