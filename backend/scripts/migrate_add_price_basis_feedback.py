"""为旧条件保留 raw 口径，新增因子及逐条反馈表；重复执行安全。"""
from sqlalchemy import inspect, text
from sqlmodel import SQLModel, create_engine
from app.config import settings
from app.models import ReviewCondition, StockAdjustmentFactor, ReviewAuditFeedback


def migrate(engine=None):
    engine = engine or create_engine(settings.database_url)
    SQLModel.metadata.create_all(engine, tables=[ReviewCondition.__table__, StockAdjustmentFactor.__table__, ReviewAuditFeedback.__table__])
    if "price_basis" not in {column["name"] for column in inspect(engine).get_columns("review_condition")}:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE review_condition ADD COLUMN price_basis VARCHAR NOT NULL DEFAULT 'raw'"))
    print("Price basis and feedback schema ready; existing rules retain their original basis")


if __name__ == "__main__":
    migrate()
