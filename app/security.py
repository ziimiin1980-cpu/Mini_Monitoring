"""Защита приложения: проверка Host, CSRF-токены, вход по паролю."""

import secrets
import time
from collections import defaultdict

from fastapi import Form, HTTPException, Request, status

from app.config import settings

CSRF_COOKIE_NAME = "csrf_token"
CSRF_FIELD_NAME = "csrf_token"

# Сколько попыток входа разрешено и за какой период
LOGIN_ATTEMPTS_LIMIT = 5
LOGIN_WINDOW_SECONDS = 300

# Попытки входа: ключ (адрес клиента) -> список отметок времени
_login_attempts: dict[str, list[float]] = defaultdict(list)


class LoginRequired(Exception):
    """Выбрасывается зависимостью, когда нужен вход: обрабатывается переадресацией."""


def allowed_host_set() -> set[str]:
    return {host.strip().lower() for host in settings.allowed_hosts.split(",") if host.strip()}


def is_host_allowed(request: Request) -> bool:
    """Разрешаем только свои хосты: защита от DNS-rebinding."""
    host = request.headers.get("host", "").split(":")[0].lower()
    return host in allowed_host_set()


def auth_enabled() -> bool:
    return bool(settings.app_password)


def verify_csrf(request: Request, csrf_token: str = Form("")) -> None:
    """Сверяет токен из формы с cookie: чужая страница такой POST отправить не сможет."""
    expected = request.cookies.get(CSRF_COOKIE_NAME, "")
    if not expected or not secrets.compare_digest(csrf_token, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Форма устарела — обновите страницу и попробуйте снова",
        )


def require_auth(request: Request) -> None:
    """Защита API: без входа отдаём 401."""
    if not auth_enabled() or request.session.get("user"):
        return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется вход")


def require_auth_page(request: Request) -> None:
    """Защита страниц: без входа перенаправляем на /login."""
    if not auth_enabled() or request.session.get("user"):
        return
    raise LoginRequired()


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def login_blocked(request: Request) -> bool:
    """Слишком много неудачных попыток за последние минуты?"""
    key = _client_key(request)
    now = time.monotonic()
    attempts = [moment for moment in _login_attempts[key] if now - moment < LOGIN_WINDOW_SECONDS]
    _login_attempts[key] = attempts
    return len(attempts) >= LOGIN_ATTEMPTS_LIMIT


def register_failed_login(request: Request) -> None:
    _login_attempts[_client_key(request)].append(time.monotonic())


def reset_login_attempts(request: Request) -> None:
    _login_attempts.pop(_client_key(request), None)
