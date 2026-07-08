from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """모든 모델의 베이스. 스키마 원천은 db/migrations/001_init.sql — 모델은 이를 미러링한다."""
