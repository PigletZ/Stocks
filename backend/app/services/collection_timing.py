"""按上海时区区分盘中、正常等候及逾期待补齐；不猜测交易日。"""
from datetime import datetime,time,timedelta,timezone
from .runtime_state import get_preferences,utc_now

SH=timezone(timedelta(hours=8))


def collection_target(now=None):
    local=(now or utc_now()).astimezone(SH)
    # 截止自然日仅限定查询区间，真正交易日仍由官方日历选出。
    return local.date() if local.hour>=15 else local.date()-timedelta(days=1)


def waiting_deadline(day,now=None):
    now=now or utc_now();local=now.astimezone(SH)
    deadline=datetime.combine(day,time(get_preferences().data_ready_hour)).replace(tzinfo=SH)
    return deadline.astimezone(timezone.utc) if day==local.date() and now<deadline else None


def record_missing(day,message,count=1,now=None):
    from .job_monitor import record_progress
    deadline=waiting_deadline(day,now)
    if deadline:
        record_progress(waiting=count,waiting_until=deadline.isoformat(),message=message+'；尚在正常等候窗口',unit='数据集')
    else:
        record_progress(deferred=count,message=message,unit='数据集')
