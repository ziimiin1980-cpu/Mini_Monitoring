import secrets

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.config import settings
from app.pages import templates
from app.security import (
    auth_enabled,
    login_blocked,
    register_failed_login,
    reset_login_attempts,
    verify_csrf,
)

router = APIRouter(tags=["Вход"])


def _render_login(
    request: Request, error: str | None = None, status_code: int = 200
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "login.html",
        {"page_title": "Вход", "error": error},
        status_code=status_code,
    )


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_form(request: Request) -> Response:
    if not auth_enabled():
        return RedirectResponse("/", status_code=303)
    return _render_login(request)


@router.post("/login", dependencies=[Depends(verify_csrf)], include_in_schema=False)
def login(request: Request, password: str = Form("")) -> Response:
    if not auth_enabled():
        return RedirectResponse("/", status_code=303)

    if login_blocked(request):
        return _render_login(
            request,
            "Слишком много неудачных попыток. Подождите несколько минут.",
            status_code=429,
        )

    if not secrets.compare_digest(password, settings.app_password):
        register_failed_login(request)
        return _render_login(request, "Неверный пароль", status_code=401)

    reset_login_attempts(request)
    request.session["user"] = "admin"
    return RedirectResponse("/", status_code=303)


@router.post(
    "/logout",
    dependencies=[Depends(verify_csrf)],
    include_in_schema=False,
)
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
