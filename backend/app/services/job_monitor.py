"""为现有 cron 脚本记录真实的执行结果；不改变调度方式。"""
import os
import threading
import time
from contextvars import ContextVar
from functools import wraps

from .runtime_state import RuntimeStore, redact, utc_now

try:
    import fcntl
except ImportError:  # 本地 Windows 验证；生产 Linux 使用跨进程 flock。
    fcntl = None

_active_run = ContextVar("stocks_job_run", default=None)
_local_locks = {}


def process_identity(pid):
    try:
        # /proc 的启动 tick 可避免旧记录碰巧遇到已复用的 PID。
        from pathlib import Path
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def process_alive(record):
    try:
        os.kill(int(record["pid"]), 0)
        identity = process_identity(record["pid"])
        return not record.get("process_identity") or identity == record["process_identity"]
    except (OSError, ValueError, KeyError, TypeError):
        return False


class JobRun:
    def __init__(self, key, store=None):
        self.key = key
        self.store = store or RuntimeStore()
        previous = self.store.read(f"job-{key}") or {}
        fields = ("started_at", "finished_at", "status", "succeeded", "failed", "skipped", "written_rows", "message")
        history = previous.get("history", [])
        if not isinstance(history, list):
            history = []
        if previous.get("started_at"):
            history = [{name: previous.get(name) for name in fields}] + history
        self.data = {"key": key, "run_id": utc_now().isoformat(), "started_at": utc_now().isoformat(),
                     "finished_at": None, "updated_at": utc_now().isoformat(), "status": "running",
                     "pid": os.getpid(), "process_identity": process_identity(os.getpid()),
                     "succeeded": 0, "failed": 0, "skipped": 0, "written_rows": 0,
                     "unit": "项", "message": "正在执行", "confirmed_skip": False, "errors": [], "history": history[:5]}
        self._last_write = 0

    def write(self, force=False):
        if force or time.monotonic() - self._last_write >= 2:
            self.data["updated_at"] = utc_now().isoformat()
            self.store.write(f"job-{self.key}", self.data)
            self._last_write = time.monotonic()

    def record(self, succeeded=0, failed=0, skipped=0, written_rows=0, message=None, unit=None, confirmed_skip=False):
        for name, value in (("succeeded", succeeded), ("failed", failed), ("skipped", skipped), ("written_rows", written_rows)):
            self.data[name] += value
        if message:
            self.data["message"] = redact(message)[:250]
            if failed:
                self.data["errors"] = (self.data["errors"] + [redact(message)[:250]])[-5:]
        if unit:
            self.data["unit"] = unit
        if confirmed_skip:
            self.data["confirmed_skip"] = True
        self.write()

    def finish(self, error=None):
        if error is not None:
            self.record(failed=1, message=str(error))
        self.data["status"] = ("partial" if self.data["failed"] and self.data["succeeded"] else
                               "error" if self.data["failed"] else
                               "success" if self.data["succeeded"] else
                               "skipped" if self.data["skipped"] and self.data["confirmed_skip"] else "unknown")
        self.data["finished_at"] = utc_now().isoformat()
        if not self.data["failed"]:
            self.data["message"] = "执行完成" if self.data["succeeded"] else self.data["message"]
        if self.data["status"] == "unknown":
            self.data["message"] = "执行已结束，但没有可核验的成功结果；请检查无数据或跳过的原因"
        self.write(force=True)


def record_progress(**values):
    run = _active_run.get()
    if run is not None:
        run.record(**values)


def tracked_job(key):
    def decorate(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            store = RuntimeStore()
            store.directory.mkdir(parents=True, exist_ok=True)
            handle = (store.directory / f"job-{key}.lock").open("a+")
            local_lock = _local_locks.setdefault(key, threading.Lock())
            locked = False
            try:
                try:
                    if fcntl:
                        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        locked = True
                    else:
                        locked = local_lock.acquire(blocking=False)
                        if not locked:
                            raise BlockingIOError()
                except BlockingIOError:
                    print("相同任务正在运行，本次跳过，保留当前运行记录", flush=True)
                    return None
                run = JobRun(key, store)
                token = _active_run.set(run)
                run.write(force=True)
                try:
                    result = function(*args, **kwargs)
                except BaseException as error:
                    run.finish(error)
                    raise
                else:
                    run.finish()
                    return result
                finally:
                    _active_run.reset(token)
            finally:
                if locked and not fcntl:
                    local_lock.release()
                handle.close()
        return wrapper
    return decorate
