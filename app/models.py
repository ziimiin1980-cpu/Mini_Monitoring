from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Target(Base):
    """Цель мониторинга: сайт/API, хост с портом или локальный процесс."""

    __tablename__ = "targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Понятное имя цели, например "Сайт компании"
    name: Mapped[str] = mapped_column(String(100), unique=True)
    # Тип проверки: http | tcp | process
    type: Mapped[str] = mapped_column(String(20))
    # Параметры проверки зависят от типа:
    #   http    -> {"url": "...", "expected_status": 200, "method": "GET"}
    #   tcp     -> {"host": "...", "port": 443}
    #   process -> {"name": "nginx.exe"}
    config: Mapped[dict] = mapped_column(JSON)
    interval_seconds: Mapped[int] = mapped_column(Integer, server_default="60")
    timeout_seconds: Mapped[int] = mapped_column(Integer, server_default="5")
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CheckResult(Base):
    """Результат одной проверки цели."""

    __tablename__ = "check_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("targets.id", ondelete="CASCADE"))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ok: Mapped[bool] = mapped_column(Boolean)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    status_code: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSON)

    # Индекс нужен для быстрой выборки истории по цели с сортировкой по времени
    __table_args__ = (Index("ix_check_results_target_checked", "target_id", "checked_at"),)
