import time
from typing import Any

import httpx

from app.checks.base import CheckOutcome


def check_http(config: dict[str, Any], timeout: float = 5) -> CheckOutcome:
    """Проверяет адрес по HTTP и сравнивает код ответа с ожидаемым."""
    url = str(config.get("url", "")).strip()
    method = str(config.get("method", "GET")).upper()
    try:
        expected_status = int(config.get("expected_status", 200))
    except (TypeError, ValueError):
        return CheckOutcome(ok=False, error="expected_status должен быть числом")

    if not url:
        return CheckOutcome(ok=False, error="В параметрах проверки не указан url")

    started = time.perf_counter()
    try:
        # follow_redirects=True: нам важен конечный адрес, а не сам редирект
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.request(method, url)
    except httpx.TimeoutException:
        return CheckOutcome(
            ok=False,
            latency_ms=_elapsed_ms(started),
            error=f"Таймаут: {timeout:g} с",
            details={"url": url},
        )
    except Exception as exc:
        # Сеть, DNS, неверный адрес — любая проблема означает «проверка не прошла»
        return CheckOutcome(
            ok=False,
            latency_ms=_elapsed_ms(started),
            error=f"Ошибка запроса: {exc}",
            details={"url": url},
        )

    ok = response.status_code == expected_status
    return CheckOutcome(
        ok=ok,
        latency_ms=_elapsed_ms(started),
        status_code=response.status_code,
        error=None
        if ok
        else f"Ожидался код {expected_status}, получен {response.status_code}",
        details={"url": url, "final_url": str(response.url)},
    )


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
