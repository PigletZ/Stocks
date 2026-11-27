"""宽基资金观察增量迁移；保留已有 ETF 缓存、复盘和异动记录。"""
from sqlmodel import SQLModel, create_engine
from app.config import settings
from app.models import BroadFundBatch, BroadFundEvidence


def migrate(engine=None):
    SQLModel.metadata.create_all(engine or create_engine(settings.database_url), tables=[
        BroadFundBatch.__table__, BroadFundEvidence.__table__])
    print('Broad-fund observation schema ready')


if __name__ == '__main__':migrate()
