import logging
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.checks import run_check
from app.config import settings
from app.db import SessionLocal
from app.models import CheckResult, Target

logger = logging.getLogger(__name__)

# Как часто планировщик просыпается и смотрит, какие цели пора проверить
CHECK_TICK_SECONDS = settings.check_tick_seconds
# Сколько дней хранить историю проверок
RETENTION_DAYS = settings.retention_days
# Как часто удалять устаревшую историю
CLEANUP_INTERVAL_SECONDS = 3600


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def run_due_checks(
    session: Session,
    last_run: dict[int, datetime],
    now: datetime | None = None,
) -> int:
    """Проверяет включённые цели, у которых истёк интервал.

    last_run — словарь «id цели → когда её проверяли в последний раз».
    Возвращает количество выполненных проверок.
    """
    now = now or _utcnow()
    checked = 0

    # Читаем не ORM-объекты, а простые значения. После отката транзакции
    # ORM-объекты становятся недействительными (обращение падает с
    # ObjectDeletedError, если строку успели удалить), а кортежи — нет.
    rows = session.execute(
        select(
            Target.id,
            Target.name,
            Target.type,
            Target.config,
            Target.timeout_seconds,
            Target.interval_seconds,
        ).where(Target.enabled.is_(True))
    ).all()

    # Забываем цели, которых больше нет или которые выключены,
    # чтобы словарь не рос бесконечно
    current_ids = {row[0] for row in rows}
    for stale_id in [target_id for target_id in last_run if target_id not in current_ids]:
        last_run.pop(stale_id, None)

    for target_id, name, target_type, config, timeout, interval_seconds in rows:
        previous = last_run.get(target_id)
        if previous is not None:
            elapsed = (now - previous).total_seconds()
            if elapsed < interval_seconds:
                continue

        # Отмечаем время до самой проверки: даже если она «зависнет» или упадёт,
        # следующая попытка не начнётся в тот же миг.
        last_run[target_id] = now

        outcome = run_check(target_type, config, timeout=timeout)

        session.add(
            CheckResult(
                target_id=target_id,
                checked_at=now,
                ok=outcome.ok,
                latency_ms=outcome.latency_ms,
                status_code=outcome.status_code,
                error=outcome.error,
                details=outcome.details,
            )
        )

        # Сохраняем каждую проверку отдельно: ошибка на одной цели
        # не должна отменять результаты остальных.
        try:
            session.commit()
        except IntegrityError:
            # Типичный случай: цель удалили, пока шла проверка
            session.rollback()
            logger.warning(
                "Цель '%s' удалена во время проверки — результат не сохранён", name
            )
            continue
        except Exception:
            session.rollback()
            logger.exception(
                "Не удалось сохранить результат проверки цели '%s'", name
            )
            continue

        checked += 1
        if outcome.ok:
            logger.info("Цель '%s': ok, %s мс", name, outcome.latency_ms)
        else:
            logger.warning("Цель '%s': ошибка — %s", name, outcome.error)

    return checked


def cleanup_old_results(
    session: Session,
    days: int = RETENTION_DAYS,
    now: datetime | None = None,
) -> int:
    """Удаляет результаты проверок старше указанного числа дней."""
    now = now or _utcnow()
    cutoff = now - timedelta(days=days)

    result = session.execute(
        delete(CheckResult).where(CheckResult.checked_at < cutoff)
    )
    session.commit()

    deleted = result.rowcount or 0
    if deleted:
        logger.info("Удалено устаревших результатов проверок: %s", deleted)
    return deleted


class Scheduler:
    """Фоновый поток, который периодически запускает проверки целей."""

    def __init__(
        self,
        tick_seconds: int = CHECK_TICK_SECONDS,
        retention_days: int = RETENTION_DAYS,
    ) -> None:
        self._tick_seconds = tick_seconds
        self._retention_days = retention_days
        self._last_run: dict[int, datetime] = {}
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_cleanup: datetime | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="mini-monitoring-scheduler", daemon=True
        )
        self._thread.start()
        logger.info(
            "Планировщик проверок запущен (проверка каждые %s с)", self._tick_seconds
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._tick_seconds + 5)
            self._thread = None
        logger.info("Планировщик проверок остановлен")

    def tick(self) -> int:
        """Один проход: проверки «просроченных» целей и, раз в час, очистка истории."""
        now = _utcnow()
        with SessionLocal() as session:
            checked = run_due_checks(session, self._last_run, now)

            if (
                self._last_cleanup is None
                or (now - self._last_cleanup).total_seconds()
                >= CLEANUP_INTERVAL_SECONDS
            ):
                cleanup_old_results(session, self._retention_days, now)
                self._last_cleanup = now

        return checked

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.tick()
            except Exception:
                # Планировщик не должен умирать из-за одной ошибки
                logger.exception("Ошибка в цикле планировщика")
            self._stop_event.wait(self._tick_seconds)


# Один экземпляр на приложение: его запускает и останавливает main.py
scheduler = Scheduler()
