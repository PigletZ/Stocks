"""按真实交易日补齐股票因子与 ETF 因子缓存；可独立回填或由晚间任务调用。"""
import argparse
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session
from app.database import engine
from app.services.etf_service import EtfService
from app.services.price_basis import StockFactorService
from app.services.review_workbench import today_shanghai
from app.services.job_monitor import tracked_job, record_progress
from app.services.collection_timing import collection_target,record_missing
from app.services.runtime_state import utc_now
from app.services.price_basis import normalize_factors


def sync_recent_factors(session, target, days=3):
    etf = EtfService()
    dates = etf._fetch_trade_dates(target-timedelta(days=days*3+20), target)[-days:]
    stock = StockFactorService()
    for day in dates:
        for kind in ('stock', 'fund'):
            try:
                skipped = False
                if kind == 'stock':
                    count = stock.sync_day(session, day)
                    skipped = stock.last_skipped
                else:
                    key = 'factor-'+day.strftime('%Y%m%d')
                    before = etf._frame_cache.get(key)
                    valid_cached=False
                    if before and (utc_now()-before[0]).total_seconds()<86400:
                        try:valid_cached=not normalize_factors(before[1],day=day).empty
                        except (ValueError,TypeError,KeyError):pass
                    frame = before[1] if valid_cached else etf._fetch_etf_factors_for_date(day)
                    count = len(frame)
                    after = etf._frame_cache.get(key)
                    skipped = bool(before and after and before[0] == after[0])
                record_progress(succeeded=int(count > 0 and not skipped), skipped=int(skipped), confirmed_skip=skipped,
                    written_rows=0 if skipped else count, unit='数据集',
                    message=f'{day} {kind} 复权因子：'+('已有同日缓存' if skipped else f'已写入 {count} 条' if count else '尚未取得，等待补齐'))
                if count==0:record_missing(day,f'{day} {kind} 复权因子尚未取得，等待补齐')
                print(f'factor {day} {kind}: rows={count}, cached={skipped}', flush=True)
            except Exception as error:
                session.rollback()
                record_progress(failed=1, message=f'{day} {kind} 复权因子：{error}', unit='数据集')
                print(f'factor {day} {kind}: failed ({type(error).__name__})', flush=True)


@tracked_job('factor-backfill')
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=35)
    args = parser.parse_args()
    if not 1 <= args.days <= 90:
        parser.error('--days must be between 1 and 90')
    with Session(engine) as session:
        sync_recent_factors(session, collection_target(), args.days)


if __name__ == '__main__':
    main()
