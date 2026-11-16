from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# Движок — «пул соединений» с базой данных.
# pool_pre_ping проверяет соединение перед использованием и переподключается,
# если PostgreSQL перезапускался.
engine = create_engine(settings.database_url, pool_pre_ping=True)

# Фабрика сессий: каждая сессия — отдельный «разговор» с базой.
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Базовый класс для всех моделей (таблиц) приложения."""


def get_db() -> Generator[Session]:
    """Открывает сессию базы данных на время запроса и закрывает её после."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
