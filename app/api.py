from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Target
from app.schemas import TargetCreate, TargetRead

router = APIRouter(prefix="/api/targets", tags=["Цели мониторинга"])

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
