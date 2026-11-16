from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import CheckResult, Target

# Пути считаем от файла модуля, а не от текущего каталога:
# так страницы работают независимо от того, откуда запущен uvicorn.
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

router = APIRouter(tags=["Страницы"])

HISTORY_LIMIT = 50


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard(request: Request) -> HTMLResponse:
    """Главная страница: таблица целей, данные подтягиваются из /api/status."""
    return templates.TemplateResponse(
        request, "index.html", {"page_title": "Mini Monitoring"}
    )


@router.get(
    "/targets/{target_id}", response_class=HTMLResponse, include_in_schema=False
)
def target_page(
    request: Request, target_id: int, db: Session = Depends(get_db)
) -> HTMLResponse:
    """Страница одной цели с параметрами и историей проверок."""
    target = db.get(Target, target_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Цель не найдена"
        )

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
            "history": history,
        },
    )
