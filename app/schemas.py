from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.messages import format_errors

TargetType = Literal["http", "tcp", "process"]


class HttpCheckConfig(BaseModel):
    """Параметры HTTP-проверки."""

    model_config = ConfigDict(extra="forbid")

    url: HttpUrl = Field(description="Адрес, который проверяем")
    method: Literal["GET", "HEAD"] = Field(
        default="GET", description="HTTP-метод проверки"
    )
    expected_status: int = Field(
        default=200, ge=100, le=599, description="Какой код ответа считается успехом"
    )
    accept_any_status: bool = Field(
        default=False,
        description=(
            "Считать успехом любой ответ сервера, кроме 5xx. "
            "Удобно для проверки доступности, когда сайт отвечает 403 или 404"
        ),
    )
    user_agent: str | None = Field(
        default=None,
        max_length=255,
        description="Свой User-Agent вместо браузерного (необязательно)",
    )


class TcpCheckConfig(BaseModel):
    """Параметры проверки TCP-порта."""

    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, max_length=255, description="Хост или IP-адрес")
    port: int = Field(ge=1, le=65535, description="TCP-порт")


class ProcessCheckConfig(BaseModel):
    """Параметры проверки локального процесса."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        min_length=1, max_length=255, description="Имя процесса, например nginx.exe"
    )


CHECK_CONFIGS: dict[str, type[BaseModel]] = {
    "http": HttpCheckConfig,
    "tcp": TcpCheckConfig,
    "process": ProcessCheckConfig,
}


class TargetCreate(BaseModel):
    """Данные для создания цели мониторинга."""

    name: str = Field(min_length=1, max_length=100, description="Понятное имя цели")
    type: TargetType = Field(description="Тип проверки: http, tcp или process")
    config: dict[str, Any] = Field(description="Параметры проверки, зависят от типа")
    interval_seconds: int = Field(
        default=60, ge=5, le=86400, description="Как часто проверять, в секундах"
    )
    timeout_seconds: int = Field(
        default=5, ge=1, le=60, description="Таймаут одной проверки, в секундах"
    )
    enabled: bool = Field(default=True, description="Включена ли цель")

    @model_validator(mode="after")
    def validate_and_normalize_config(self) -> "TargetCreate":
        """Проверяет config по правилам выбранного типа и сохраняет его в едином виде."""
        config_schema = CHECK_CONFIGS[self.type]
        try:
            parsed = config_schema.model_validate(self.config)
        except ValueError as exc:
            # Переводим ошибку вложенной схемы в понятное сообщение
            problems = _format_validation_error(exc)
            raise ValueError(
                f"Некорректные параметры для типа '{self.type}': {problems}"
            ) from exc

        self.config = parsed.model_dump(mode="json", exclude_none=True)
        return self


class TargetRead(BaseModel):
    """Цель мониторинга в том виде, в каком её отдаёт API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    config: dict[str, Any]
    interval_seconds: int
    timeout_seconds: int
    enabled: bool
    created_at: datetime
    updated_at: datetime


class LastCheck(BaseModel):
    """Последняя проверка цели."""

    model_config = ConfigDict(from_attributes=True)

    checked_at: datetime
    ok: bool
    latency_ms: int | None
    status_code: int | None
    error: str | None


class TargetStatus(TargetRead):
    """Цель вместе с её текущим состоянием."""

    last_check: LastCheck | None = None
    uptime_24h: float | None = Field(
        default=None,
        description="Доля успешных проверок за 24 часа, %. null — проверок не было",
    )
    checks_24h: int = Field(default=0, description="Сколько проверок было за 24 часа")


class HistoryItem(BaseModel):
    """Одна запись истории проверок."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    checked_at: datetime
    ok: bool
    latency_ms: int | None
    status_code: int | None
    error: str | None
    details: dict[str, Any] | None


def _format_validation_error(exc: ValueError) -> str:
    """Собирает ошибки Pydantic в одну читаемую строку (по-русски)."""
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return str(exc)
    return format_errors(errors())
