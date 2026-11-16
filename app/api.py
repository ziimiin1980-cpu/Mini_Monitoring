from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.checks import run_check
from app.db import get_db
from app.models import CheckResult, Target
from app.schemas import (
    HistoryItem,
    LastCheck,
    TargetCreate,
    TargetRead,
    TargetStatus,
)

router = APIRouter(prefix="/api/targets", tags=["Цели мониторинга"])
status_router = APIRouter(prefix="/api", tags=["Статусы и история"])

# За какой период считаем «доступность» цели
UPTIME_WINDOW_HOURS = 24

DUPLICATE_NAME_MESSAGE = "Цель с таким именем уже существует"


def _get_target_or_404(db: Session, target_id: int) -> Target:
    target = db.get(Target, target_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Цель не найдена"
        )
    return target


def _commit(db: Session) -> None:
    """Сохраняет изменения и переводит конфликт уникального имени в ответ 409."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=DUPLICATE_NAME_MESSAGE
        )


@router.get("", response_model=list[TargetRead], summary="Список целей мониторинга")
def list_targets(db: Session = Depends(get_db)) -> list[Target]:
    return list(db.scalars(select(Target).order_by(Target.id)))


@router.get("/{target_id}", response_model=TargetRead, summary="Одна цель по id")
def get_target(target_id: int, db: Session = Depends(get_db)) -> Target:
    return _get_target_or_404(db, target_id)


@router.post(
    "",
    response_model=TargetRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать цель",
)
def create_target(payload: TargetCreate, db: Session = Depends(get_db)) -> Target:
    target = Target(**payload.model_dump())
    db.add(target)
    _commit(db)
    db.refresh(target)
    return target


@router.put(
    "/{target_id}",
    response_model=TargetRead,
    summary="Изменить цель целиком",
)
def update_target(
    target_id: int, payload: TargetCreate, db: Session = Depends(get_db)
) -> Target:
    target = _get_target_or_404(db, target_id)
    for field, value in payload.model_dump().items():
        setattr(target, field, value)
    _commit(db)
    db.refresh(target)
    return target


@router.delete(
    "/{target_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить цель",
)
def delete_target(target_id: int, db: Session = Depends(get_db)) -> None:
    target = _get_target_or_404(db, target_id)
    db.delete(target)
    db.commit()


@router.get(
    "/{target_id}/history",
    response_model=list[HistoryItem],
    summary="История проверок цели",
)
def get_history(
    target_id: int,
    limit: int = Query(
        100, ge=1, le=1000, description="Сколько последних проверок вернуть"
    ),
    db: Session = Depends(get_db),
) -> list[CheckResult]:
    _get_target_or_404(db, target_id)
    return list(
        db.scalars(
            select(CheckResult)
            .where(CheckResult.target_id == target_id)
            .order_by(CheckResult.checked_at.desc())
            .limit(limit)
        )
    )


@router.post(
    "/{target_id}/check",
    response_model=HistoryItem,
    status_code=status.HTTP_201_CREATED,
    summary="Проверить цель немедленно",
)
def check_target_now(target_id: int, db: Session = Depends(get_db)) -> CheckResult:
    target = _get_target_or_404(db, target_id)
    outcome = run_check(target.type, target.config, timeout=target.timeout_seconds)

    result = CheckResult(
        target_id=target.id,
        checked_at=datetime.now(timezone.utc),
        ok=outcome.ok,
        latency_ms=outcome.latency_ms,
        status_code=outcome.status_code,
        error=outcome.error,
        details=outcome.details,
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return result


@status_router.get(
    "/status",
    response_model=list[TargetStatus],
    summary="Текущее состояние всех целей",
)
def get_status(db: Session = Depends(get_db)) -> list[TargetStatus]:
    since = datetime.now(timezone.utc) - timedelta(hours=UPTIME_WINDOW_HOURS)

    # За последние 24 часа: сколько всего проверок и сколько успешных
    aggregates = {
        target_id: (total, ok_count)
        for target_id, total, ok_count in db.execute(
            select(
                CheckResult.target_id,
                func.count(),
                func.sum(case((CheckResult.ok.is_(True), 1), else_=0)),
            )
            .where(CheckResult.checked_at >= since)
            .group_by(CheckResult.target_id)
        ).all()
    }

    items: list[TargetStatus] = []
    for target in db.scalars(select(Target).order_by(Target.id)):
        # Последняя проверка. Целей пока немного, поэтому отдельный запрос
        # на каждую — так код остаётся понятным; при росте их числа оптимизируем.
        last = db.scalars(
            select(CheckResult)
            .where(CheckResult.target_id == target.id)
            .order_by(CheckResult.checked_at.desc())
            .limit(1)
        ).first()

        total, ok_count = aggregates.get(target.id, (0, 0))

        item = TargetStatus.model_validate(target)
        item.last_check = LastCheck.model_validate(last) if last else None
        item.checks_24h = total
        item.uptime_24h = round(ok_count / total * 100, 1) if total else None
        items.append(item)

    return items
