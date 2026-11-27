"""游资动向增量迁移，重复执行安全，不改写原龙虎榜和复盘记录。"""
from sqlmodel import SQLModel, create_engine
from app.config import settings
from app.models import HotMoneyCatalog, SeatDisclosureBatch, SeatFollow


def migrate(engine=None):
    SQLModel.metadata.create_all(engine or create_engine(settings.database_url), tables=[
        HotMoneyCatalog.__table__, SeatDisclosureBatch.__table__, SeatFollow.__table__])
    print('Hot-money disclosure schema ready')


if __name__ == '__main__':
    migrate()
