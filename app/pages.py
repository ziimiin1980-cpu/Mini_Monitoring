from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.messages import format_errors
from app.models import CheckResult, Target
from app.schemas import TargetCreate
from app.security import CSRF_COOKIE_NAME, auth_enabled, verify_csrf

# Пути считаем от файла модуля, а не от текущего каталога:
# так страницы работают независимо от того, откуда запущен uvicorn.
BASE_DIR = Path(__file__).resolve().parent


def _template_context(request: Request) -> dict[str, Any]:
    """Общие переменные для всех шаблонов: CSRF-токен и признак включённого входа."""
    csrf_token = getattr(request.state, "csrf_token", None) or request.cookies.get(
        CSRF_COOKIE_NAME, ""
    )
    return {"csrf_token": csrf_token, "auth_enabled": auth_enabled()}


templates = Jinja2Templates(
    directory=BASE_DIR / "templates", context_processors=[_template_context]
)

router = APIRouter(tags=["Страницы"])

HISTORY_LIMIT = 50
DUPLICATE_NAME_MESSAGE = "Цель с таким именем уже существует"


def _get_target_or_404(db: Session, target_id: int) -> Target:
    target = db.get(Target, target_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Цель не найдена")
    return target


def _form_values(target: Target | None = None) -> dict[str, Any]:
    """Значения полей формы: пустые для новой цели или из существующей."""
    if target is None:
        return {
            "name": "",
            "type": "http",
            "url": "",
            "expected_status": "200",
            "status_mode": "exact",
            "host": "",
            "port": "",
            "process_name": "",
            "interval_seconds": 60,
            "timeout_seconds": 5,
            "enabled": True,
        }

    config = target.config or {}
    return {
        "name": target.name,
        "type": target.type,
        "url": config.get("url", ""),
        "expected_status": config.get("expected_status", 200),
        "status_mode": "any" if config.get("accept_any_status") else "exact",
        "host": config.get("host", ""),
        "port": config.get("port", ""),
        "process_name": config.get("name", ""),
        "interval_seconds": target.interval_seconds,
        "timeout_seconds": target.timeout_seconds,
        "enabled": target.enabled,
    }


def _error_text(exc: ValidationError) -> str:
    """Собирает ошибки Pydantic в одну понятную строку для формы."""
    return format_errors(exc.errors())


def _build_payload(
    *,
    name: str,
    target_type: str,
    url: str,
    expected_status: str,
    status_mode: str,
    host: str,
    port: str,
    process_name: str,
    interval_seconds: str,
    timeout_seconds: str,
    enabled: bool,
) -> tuple[TargetCreate | None, str | None]:
    """Собирает config под выбранный тип и проверяет его теми же схемами, что и API."""
    if target_type == "http":
        config: dict[str, Any] = {"url": url.strip()}
        if status_mode == "any":
            config["accept_any_status"] = True
        elif expected_status.strip():
            config["expected_status"] = expected_status.strip()
    elif target_type == "tcp":
        config = {"host": host.strip(), "port": port.strip()}
    elif target_type == "process":
        config = {"name": process_name.strip()}
    else:
        return None, f"Неизвестный тип проверки: {target_type}"

    try:
        payload = TargetCreate(
            name=name.strip(),
            type=target_type,
            config=config,
            interval_seconds=interval_seconds,
            timeout_seconds=timeout_seconds,
            enabled=enabled,
        )
    except ValidationError as exc:
        return None, _error_text(exc)

    return payload, None


def _render_form(
    request: Request,
    *,
    action_url: str,
    values: dict[str, Any],
    submit_label: str,
    cancel_url: str,
    error: str | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "form.html",
        {
            "page_title": submit_label,
            "action_url": action_url,
            "values": values,
            "submit_label": submit_label,
            "cancel_url": cancel_url,
            "error": error,
        },
        status_code=status_code,
    )


def _redirect(next_url: str, default: str = "/") -> RedirectResponse:
    """Переадресация только на внутренние пути (защита от подстановки чужого адреса)."""
    if next_url.startswith("/") and not next_url.startswith("//"):
        return RedirectResponse(next_url, status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(default, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard(request: Request) -> HTMLResponse:
    """Главная страница: таблица целей, данные подтягиваются из /api/status."""
    return templates.TemplateResponse(request, "index.html", {"page_title": "Mini Monitoring"})


# ВАЖНО: /targets/new объявлен раньше /targets/{target_id},
# иначе FastAPI попытается разобрать "new" как число.
@router.get("/targets/new", response_class=HTMLResponse, include_in_schema=False)
def new_target_form(request: Request) -> HTMLResponse:
    return _render_form(
        request,
        action_url="/targets/new",
        values=_form_values(),
        submit_label="Добавить цель",
        cancel_url="/",
    )


@router.post(
    "/targets/new",
    dependencies=[Depends(verify_csrf)],
    include_in_schema=False,
)
def create_target_form(
    request: Request,
    name: str = Form(""),
    type: str = Form("http"),  # noqa: A002 - имя поля формы
    url: str = Form(""),
    expected_status: str = Form("200"),
    status_mode: str = Form("exact"),
    host: str = Form(""),
    port: str = Form(""),
    process_name: str = Form(""),
    interval_seconds: str = Form("60"),
    timeout_seconds: str = Form("5"),
    enabled: bool = Form(False),
    db: Session = Depends(get_db),
):
    values = {
        "name": name,
        "type": type,
        "url": url,
        "expected_status": expected_status,
        "status_mode": status_mode,
        "host": host,
        "port": port,
        "process_name": process_name,
        "interval_seconds": interval_seconds,
        "timeout_seconds": timeout_seconds,
        "enabled": enabled,
    }

    payload, error = _build_payload(
        name=name,
        target_type=type,
        url=url,
        expected_status=expected_status,
        status_mode=status_mode,
        host=host,
        port=port,
        process_name=process_name,
        interval_seconds=interval_seconds,
        timeout_seconds=timeout_seconds,
        enabled=enabled,
    )
    if error is not None:
        return _render_form(
            request,
            action_url="/targets/new",
            values=values,
            submit_label="Добавить цель",
            cancel_url="/",
            error=error,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    target = Target(**payload.model_dump())
    db.add(target)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _render_form(
            request,
            action_url="/targets/new",
            values=values,
            submit_label="Добавить цель",
            cancel_url="/",
            error=DUPLICATE_NAME_MESSAGE,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    db.refresh(target)
    return _redirect(f"/targets/{target.id}")


def _details(target: Target) -> list[tuple[str, str]]:
    """Понятное человеку описание параметров цели (вместо сырого JSON)."""
    config = target.config or {}
    items: list[tuple[str, str]] = []

    if target.type == "http":
        items.append(("Адрес", str(config.get("url", "—"))))
        items.append(("Метод", str(config.get("method", "GET"))))
        if config.get("accept_any_status"):
            items.append(("Условие успеха", "любой ответ сервера, кроме 5xx"))
        else:
            items.append(("Ожидаемый код", str(config.get("expected_status", 200))))
        if config.get("user_agent"):
            items.append(("User-Agent", str(config["user_agent"])))
    elif target.type == "tcp":
        items.append(("Хост", str(config.get("host", "—"))))
        items.append(("Порт", str(config.get("port", "—"))))
    elif target.type == "process":
        items.append(("Имя процесса", str(config.get("name", "—"))))

    items.append(("Проверять каждые", f"{target.interval_seconds} с"))
    items.append(("Таймаут проверки", f"{target.timeout_seconds} с"))
    items.append(("Состояние", "включена" if target.enabled else "выключена"))
    return items


@router.get("/targets/{target_id}", response_class=HTMLResponse, include_in_schema=False)
def target_page(request: Request, target_id: int, db: Session = Depends(get_db)) -> HTMLResponse:
    """Страница одной цели с параметрами и историей проверок."""
    target = _get_target_or_404(db, target_id)

    history = db.scalars(
        select(CheckResult)
        .where(CheckResult.target_id == target_id)
        .order_by(CheckResult.checked_at.desc())
        .limit(HISTORY_LIMIT)
    ).all()

    return templates.TemplateResponse(
        request,
        "target.html",
        {
            "page_title": target.name,
            "target": target,
            "details": _details(target),
            "history": history,
        },
    )


@router.get("/targets/{target_id}/edit", response_class=HTMLResponse, include_in_schema=False)
def edit_target_form(
    request: Request, target_id: int, db: Session = Depends(get_db)
) -> HTMLResponse:
    target = _get_target_or_404(db, target_id)
    return _render_form(
        request,
        action_url=f"/targets/{target_id}/edit",
        values=_form_values(target),
        submit_label="Сохранить изменения",
        cancel_url=f"/targets/{target_id}",
    )


@router.post(
    "/targets/{target_id}/edit",
    dependencies=[Depends(verify_csrf)],
    include_in_schema=False,
)
def update_target_form(
    request: Request,
    target_id: int,
    name: str = Form(""),
    type: str = Form("http"),  # noqa: A002 - имя поля формы
    url: str = Form(""),
    expected_status: str = Form("200"),
    status_mode: str = Form("exact"),
    host: str = Form(""),
    port: str = Form(""),
    process_name: str = Form(""),
    interval_seconds: str = Form("60"),
    timeout_seconds: str = Form("5"),
    enabled: bool = Form(False),
    db: Session = Depends(get_db),
):
    target = _get_target_or_404(db, target_id)

    values = {
        "name": name,
        "type": type,
        "url": url,
        "expected_status": expected_status,
        "status_mode": status_mode,
        "host": host,
        "port": port,
        "process_name": process_name,
        "interval_seconds": interval_seconds,
        "timeout_seconds": timeout_seconds,
        "enabled": enabled,
    }

    payload, error = _build_payload(
        name=name,
        target_type=type,
        url=url,
        expected_status=expected_status,
        status_mode=status_mode,
        host=host,
        port=port,
        process_name=process_name,
        interval_seconds=interval_seconds,
        timeout_seconds=timeout_seconds,
        enabled=enabled,
    )
    if error is not None:
        return _render_form(
            request,
            action_url=f"/targets/{target_id}/edit",
            values=values,
            submit_label="Сохранить изменения",
            cancel_url=f"/targets/{target_id}",
            error=error,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    for field, value in payload.model_dump().items():
        setattr(target, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _render_form(
            request,
            action_url=f"/targets/{target_id}/edit",
            values=values,
            submit_label="Сохранить изменения",
            cancel_url=f"/targets/{target_id}",
            error=DUPLICATE_NAME_MESSAGE,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return _redirect(f"/targets/{target_id}")


@router.post(
    "/targets/{target_id}/toggle",
    dependencies=[Depends(verify_csrf)],
    include_in_schema=False,
)
def toggle_target(
    target_id: int,
    next: str = Form("/"),  # noqa: A002 - имя поля формы
    db: Session = Depends(get_db),
):
    target = _get_target_or_404(db, target_id)
    target.enabled = not target.enabled
    db.commit()
    return _redirect(next)


@router.post(
    "/targets/{target_id}/delete",
    dependencies=[Depends(verify_csrf)],
    include_in_schema=False,
)
def delete_target_form(target_id: int, db: Session = Depends(get_db)):
    target = _get_target_or_404(db, target_id)
    db.delete(target)
    db.commit()
    # После удаления страницы цели больше нет — уходим на дашборд
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
