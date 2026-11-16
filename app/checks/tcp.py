import socket
import time
from typing import Any

from app.checks.base import CheckOutcome


def check_tcp(config: dict[str, Any], timeout: float = 5) -> CheckOutcome:
    """Проверяет, что хост принимает TCP-соединение на указанном порту."""
    host = str(config.get("host", "")).strip()
    try:
        port = int(config.get("port", 0))
    except (TypeError, ValueError):
        return CheckOutcome(ok=False, error="Порт должен быть числом")

    if not host:
        return CheckOutcome(ok=False, error="В параметрах проверки не указан host")
    if not 1 <= port <= 65535:
        return CheckOutcome(ok=False, error=f"Некорректный порт: {port}")

    details = {"host": host, "port": port}
    started = time.perf_counter()
    try:
        # Соединение сразу закрывается: нам важен сам факт подключения
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except TimeoutError:
        return CheckOutcome(
            ok=False,
            latency_ms=_elapsed_ms(started),
            error=f"Таймаут: {timeout:g} с",
            details=details,
        )
    except OSError as exc:
        return CheckOutcome(
            ok=False,
            latency_ms=_elapsed_ms(started),
            error=f"Не удалось подключиться: {exc}",
            details=details,
        )

    return CheckOutcome(ok=True, latency_ms=_elapsed_ms(started), details=details)


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
