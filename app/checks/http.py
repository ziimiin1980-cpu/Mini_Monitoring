import time
from typing import Any

import httpx

from app.checks.base import CheckOutcome

# Многие сайты (Cloudflare, антибот-защита) отвечают 403 на запросы
# с «программным» User-Agent. Представляемся обычным браузером.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}


def check_http(config: dict[str, Any], timeout: float = 5) -> CheckOutcome:
    """Проверяет адрес по HTTP и сравнивает ответ с ожидаемым."""
    url = str(config.get("url", "")).strip()
    method = str(config.get("method", "GET")).upper()
    accept_any_status = bool(config.get("accept_any_status", False))

    try:
        expected_status = int(config.get("expected_status", 200))
    except (TypeError, ValueError):
        return CheckOutcome(ok=False, error="expected_status должен быть числом")

    if not url:
        return CheckOutcome(ok=False, error="В параметрах проверки не указан url")

    headers = dict(DEFAULT_HEADERS)
    custom_user_agent = config.get("user_agent")
    if custom_user_agent:
        headers["User-Agent"] = str(custom_user_agent)

    started = time.perf_counter()
    try:
        # follow_redirects=True: нам важен конечный адрес, а не сам редирект
        with httpx.Client(
            timeout=timeout, follow_redirects=True, headers=headers
        ) as client:
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

    ok, error = _evaluate(response.status_code, expected_status, accept_any_status)
    return CheckOutcome(
        ok=ok,
        latency_ms=_elapsed_ms(started),
        status_code=response.status_code,
        error=error,
        details={"url": url, "final_url": str(response.url)},
    )


def _evaluate(
    status_code: int, expected_status: int, accept_any_status: bool
) -> tuple[bool, str | None]:
    """Решает, считать ли ответ успехом, и объясняет причину провала."""
    if accept_any_status:
        if status_code < 500:
            return True, None
        return False, f"Сервер ответил ошибкой {status_code} (ожидался любой ответ, кроме 5xx)"

    if status_code == expected_status:
        return True, None
    return False, f"Ожидался код {expected_status}, получен {status_code}"


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
