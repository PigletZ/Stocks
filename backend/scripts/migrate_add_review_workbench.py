"""创建复盘关注与验证记录表；可重复执行，不修改旧笔记与台账。"""
from sqlmodel import SQLModel, create_engine
from app.config import settings
from app.models import ReviewObservation, ReviewVerification


if __name__ == "__main__":
    SQLModel.metadata.create_all(create_engine(settings.database_url), tables=[
        ReviewObservation.__table__, ReviewVerification.__table__,
    ])
    print("Review workbench tables ready")
