from dataclasses import dataclass
from typing import Any


@dataclass
class CheckOutcome:
    """Результат одной проверки — единый формат для всех типов проверок."""

    ok: bool
    # Сколько миллисекунд заняла проверка (для проверки процесса не считается)
    latency_ms: int | None = None
    # Код ответа HTTP (только для http-проверок)
    status_code: int | None = None
    # Текст ошибки, если проверка не прошла
    error: str | None = None
    # Дополнительные сведения: адрес, хост, pid и т.п.
    details: dict[str, Any] | None = None
