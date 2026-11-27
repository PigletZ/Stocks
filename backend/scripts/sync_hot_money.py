"""盘后同步龙虎榜单据和名录；页面读取本地版本，不回源，不调用 AI。"""
import argparse
import sys
from datetime import timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session
from app.config import settings
from app.database import engine
from app.services.collection_timing import collection_target, record_missing
from app.services.hot_money import latest_batch, publish_events, sync_day
from app.services.job_monitor import record_progress, tracked_job
from app.services.overview_service import OverviewService
from app.services.runtime_state import RuntimeStore, get_preferences, utc_now
from app.services.short_term import SH
from app.services.tushare_client import TushareClient


@tracked_job('hot-money')
def run(days=3, refresh=False, history=False):
    store, now = RuntimeStore(), utc_now()
    target = collection_target(now)
    dates = OverviewService().fetch_trade_dates(target-timedelta(days=100), target)[-days:]
    if not dates:
        raise RuntimeError('尚未取得官方交易日历，未推测工作日')
    client = TushareClient(settings.tushare_token)
    # 首先取得最近可用日；某个历史日的坏单据不阻塞其余日期补漏。
    for day in reversed(dates):
        key = 'seat-checked-'+day.strftime('%Y%m%d')
        check = store.read(key) or {}
        with Session(engine) as session:
            existing = latest_batch(session, day)
        if existing and not refresh and check.get('ready_checked'):
            record_progress(skipped=1, confirmed_skip=True, message=f'{day} 已核对并缓存，跳过重复拉取')
            continue
        try:
            with Session(engine) as session:
                batch, changed = sync_day(session, day, client, now=now)
                if batch is None:
                    record_missing(day, f'{day} 龙虎榜席位尚未发布齐备，保留旧版本')
                    store.write(key, {'status': 'waiting', 'checked_at': now.isoformat(), 'message': '本次返回空表，保留旧版本，等待后续补齐'})
                    continue
                written = publish_events(session, batch, notify=not history and changed and day == dates[-1], now=now)
                local = now.astimezone(SH)
                ready = day < local.date() or local.hour >= get_preferences().data_ready_hour
                store.write(key, {'status': 'ready', 'checked_at': now.isoformat(), 'batch_id': batch.id,
                    'ready_checked': ready, 'changed': changed, 'events_written': written,
                    'message': '已校验并缓存公开披露；可手动核对最近三日的后续订正。'})
                record_progress(succeeded=1, written_rows=int(changed), message=f'{day} 披露已校验，'+('追加新版本' if changed else '复用相同版本'))
        except Exception as error:
            store.write(key, {'status': 'error', 'checked_at': now.isoformat(), 'message': '采集或格式校验失败，保留旧版本，请核对任务结果'})
            record_progress(failed=1, message=f'{day} 披露同步失败：{error}')
            if not isinstance(error, ValueError):
                break


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, choices=range(1, 21), default=3)
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--history', action='store_true', help='初始化历史，不产生新行情提醒')
    args = parser.parse_args()
    run(args.days, args.refresh, args.history)
