"""增加规则版本、提醒状态和 AI 审阅表；可重复执行，不改写旧记录。"""
from sqlmodel import SQLModel, create_engine
from app.config import settings
from app.models import ReviewCondition, ReviewReminderState, ReviewAudit


if __name__ == "__main__":
    SQLModel.metadata.create_all(create_engine(settings.database_url), tables=[
        ReviewCondition.__table__, ReviewReminderState.__table__, ReviewAudit.__table__,
    ])
    print("Review assistant tables ready")
