"""新增分钟缓存及异动历史，重复执行安全。"""
from sqlmodel import SQLModel, create_engine
from app.config import settings
from app.models import ShortTermEvent, ShortTermEventState, ShortTermMinute


def migrate(engine=None):
    SQLModel.metadata.create_all(engine or create_engine(settings.database_url), tables=[
        ShortTermMinute.__table__, ShortTermEvent.__table__, ShortTermEventState.__table__])
    print('Short-term event schema ready')


if __name__ == '__main__':
    migrate()
