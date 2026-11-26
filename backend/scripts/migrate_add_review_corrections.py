from sqlmodel import SQLModel,create_engine
from app.config import settings
from app.models import ReviewCorrection


def migrate(engine=None):
    SQLModel.metadata.create_all(engine or create_engine(settings.database_url),tables=[ReviewCorrection.__table__])
    print('Review correction history schema ready')


if __name__=='__main__':migrate()
