"""补齐固定宽基 ETF 篮子的区间资料。页面刷新不触发行情接口或 AI。"""
import argparse
import sys
from datetime import date,datetime,time,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from sqlmodel import Session
from app.config import settings
from app.database import engine
from app.services.broad_funds import collect,save_batch,summarize,publish_events,BASKET_VERSION
from app.services.collection_timing import collection_target
from app.services.etf_service import EtfService
from app.services.job_monitor import tracked_job,record_progress
from app.services.runtime_state import RuntimeStore,utc_now
from app.services.short_term import SH
from app.services.tushare_client import TushareClient
from app.models import BroadFundBatch
from sqlmodel import select


def missing_status(day,now):
    deadline=datetime.combine(day+timedelta(days=1),time(10)).replace(tzinfo=SH)
    return ('waiting',deadline) if now < deadline else ('overdue',deadline)


@tracked_job('broad-funds')
def run(refresh=False,history=False,end_date=None):
    now=utc_now();store=RuntimeStore();target=collection_target(now)
    if end_date:
        if end_date>target:raise ValueError('截止日不能晚于最近已收盘的自然日')
        target=end_date
    dates=EtfService()._fetch_trade_dates(target-timedelta(days=120),target)[-45:]
    if len(dates)<21:raise ValueError('官方日历覆盖不足，未推测交易日')
    day=dates[-1]
    with Session(engine) as session:
        previous=session.exec(select(BroadFundBatch).where(BroadFundBatch.end_date==day)
            .order_by(BroadFundBatch.id.desc()).limit(1)).first()
        if previous and not refresh and summarize(previous,day)['source_ready']:
            record_progress(skipped=1,confirmed_skip=True,message=f'{day} 固定篮子所需资料齐备，复用已校验快照');return
        data,raw=collect(TushareClient(settings.tushare_token),dates,now)
        batch,changed=save_batch(session,data,raw,now)
        if batch is None:
            ready=False;view=None;written=0
        else:
            view=summarize(batch,day);ready=view['source_ready']
            written=publish_events(session,batch,notify=changed and not history,now=now)
        state,deadline=missing_status(day,now.astimezone(SH))
        state='ready' if ready else state
        store.write('broad-funds-check',{'status':state,'date':str(day),'checked_at':now.isoformat(),
            'batch_id':batch.id if batch else None,'market_date':view['market_date'] if view else None,
            'flow_date':view['flow_date'] if view else None,'flow_valid':view['flow_valid'] if view else 0,
            'waiting_until':deadline.isoformat() if not ready else None,
            'message':'篮子资料已齐备；单日折算或分红口径变化仍单独暂停估算。' if ready else
                '份额、净值或行情尚未齐备，保留已有资料；次日上午前为正常等待，超过后继续补漏。'})
        record_progress(succeeded=int(ready),waiting=int(state=='waiting'),deferred=int(state=='overdue'),
            waiting_until=deadline.isoformat() if state=='waiting' else None,written_rows=int(changed),
            message=f'{day} 宽基资料：'+('已齐备' if ready else '待补齐，缺失不补零')+f'；写入 {written} 条触发修订')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--refresh',action='store_true')
    parser.add_argument('--history',action='store_true')
    parser.add_argument('--end-date',type=date.fromisoformat)
    args=parser.parse_args();run(args.refresh,args.history,args.end_date)
