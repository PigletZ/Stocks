"""启动有限的维护脚本；请求只提交任务，结果来自实际执行记录。"""
import os
import subprocess
import sys
import threading
from datetime import datetime, timedelta
from typing import Literal

from .job_monitor import process_alive, process_identity
from .runtime_state import BACKEND_DIR, RuntimeStore, redact, utc_now

try:
    import fcntl
except ImportError:
    fcntl = None

Action = Literal['daily', 'factors', 'backup']
ACTIONS = {
    'daily': {'key': 'daily', 'name': '补齐近期数据', 'description': '补齐最近 3 个真实交易日的市场、板块、复盘数据和复权因子。',
              'script': 'import_daily.py', 'args': [], 'log': 'import_daily.log'},
    'factors': {'key': 'factor-backfill', 'name': '回填复权数据', 'description': '回填最近 35 个真实交易日的股票和 ETF 复权因子，已有有效缓存会复用。',
                'script': 'sync_price_factors.py', 'args': ['--days', '35'], 'log': 'sync_factors.log'},
    'backup': {'key': 'backup', 'name': '生成校验备份', 'description': '生成 SQLite 一致性备份并校验；保留现有备份文件。',
               'script': 'backup_database.py', 'args': [], 'log': 'backup.log'},
}
_launch_lock = threading.Lock()
COOLDOWN = timedelta(seconds=60)


class MaintenanceBusy(RuntimeError):
    pass


def _timestamp(value):
    try:
        result = datetime.fromisoformat(value)
        return result if result.tzinfo else None
    except (TypeError, ValueError):
        return None


def maintenance_status(action, store=None, now=None):
    store, now = store or RuntimeStore(), now or utc_now()
    spec = ACTIONS[action]
    record = store.read('job-' + spec['key'])
    receipt = store.read('maintenance-' + action)
    requested = _timestamp(receipt.get('requested_at')) if receipt else None
    started = _timestamp(record.get('started_at')) if record else None
    current = record if record and (not requested or (started and started >= requested)) else None
    status, message = 'idle', '尚未发起维护；可按需要手动执行。'
    if current:
        status, message = current.get('status', 'unknown'), redact(current.get('message', ''))
        if status == 'running' and not process_alive(current):
            status, message = 'interrupted', '任务进程已退出，未取得完成记录；可重新发起。'
    elif receipt:
        if process_alive(receipt):
            status, message = 'queued', '任务已提交，等待脚本取得执行锁；尚未确认完成。'
        else:
            status, message = 'interrupted', '任务未留下对应的完成记录，请核对同步任务或重新发起。'
    # cron 可能在手动提交之前已启动，共用脚本锁，直接展示该次执行。
    if record and record.get('status') == 'running' and process_alive(record):
        current, status, message = record, 'running', redact(record.get('message', '正在执行'))
    next_allowed = requested + COOLDOWN if requested else None
    cooling = next_allowed is not None and now < next_allowed
    return {'action': action, 'name': spec['name'], 'description': spec['description'],
            'status': status, 'message': message, 'requested_at': requested.isoformat() if requested else None,
            'next_allowed_at': next_allowed.isoformat() if cooling else None,
            'can_start': status not in ('running', 'queued') and not cooling, 'record': current}


def maintenance_statuses(store=None, now=None):
    return [maintenance_status(action, store, now) for action in ACTIONS]


def start_maintenance(action, store=None, now=None, backend=None):
    if action not in ACTIONS:
        raise ValueError('不支持的维护任务')
    store, now = store or RuntimeStore(), now or utc_now()
    backend = backend or BACKEND_DIR
    store.directory.mkdir(parents=True, exist_ok=True)
    if not _launch_lock.acquire(blocking=False):
        raise MaintenanceBusy('正在提交维护任务，请稍后刷新状态。')
    try:
        with (store.directory / 'maintenance-launch.lock').open('a+') as handle:
            try:
                if fcntl:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise MaintenanceBusy('正在提交维护任务，请稍后刷新状态。') from None
            existing = maintenance_status(action, store, now)
            if not existing['can_start']:
                return {'accepted': False, 'job': existing}
            spec = ACTIONS[action]
            script = backend / 'scripts' / spec['script']
            if not script.is_file():
                raise OSError('Maintenance script unavailable')
            log_dir = backend / 'logs'
            log_dir.mkdir(parents=True, exist_ok=True)
            options = {'start_new_session': True} if os.name != 'nt' else {'creationflags': subprocess.CREATE_NO_WINDOW}
            with (log_dir / spec['log']).open('ab') as output:
                child = subprocess.Popen([sys.executable, '-u', str(script), *spec['args']],
                    cwd=backend, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, **options)
            try:
                store.write('maintenance-' + action, {'requested_at': now.isoformat(), 'pid': child.pid,
                    'process_identity': process_identity(child.pid)})
            except OSError:
                child.terminate()
                child.wait(timeout=10)
                raise
            # 回收子进程，不用等待 HTTP 请求或维持页面打开。
            threading.Thread(target=child.wait, daemon=True).start()
            return {'accepted': True, 'job': maintenance_status(action, store, now)}
    finally:
        _launch_lock.release()
