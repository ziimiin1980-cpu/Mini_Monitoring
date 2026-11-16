from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, delete, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.checks.base import CheckOutcome
from app.db import Base
from app.models import CheckResult, Target
from app.scheduler import Scheduler, cleanup_old_results, run_due_checks

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _record):
    # По умолчанию SQLite не проверяет внешние ключи — включаем,
    # чтобы тесты вели себя как PostgreSQL.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestingSessionLocal = sessionmaker(
    bind=engine, autoflush=False, expire_on_commit=False
)


@pytest.fixture
def session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def make_target(
    session,
    name="Сайт",
    type_="http",
    config=None,
    interval_seconds=60,
    enabled=True,
):
    target = Target(
        name=name,
        type=type_,
        config=config or {"url": "https://example.com"},
        interval_seconds=interval_seconds,
        timeout_seconds=5,
        enabled=enabled,
    )
    session.add(target)
    session.commit()
    session.refresh(target)
    return target


def fake_checker(outcome):
    def _run(target_type, config, timeout=5):
        return outcome

    return _run


def test_checks_only_enabled_targets(session, monkeypatch):
    monkeypatch.setattr(
        "app.scheduler.run_check", fake_checker(CheckOutcome(ok=True, latency_ms=5))
    )
    enabled = make_target(session, name="Включена")
    make_target(session, name="Выключена", enabled=False)

    checked = run_due_checks(session, {}, datetime.now(timezone.utc))

    results = session.scalars(select(CheckResult)).all()
    assert checked == 1
    assert len(results) == 1
    assert results[0].target_id == enabled.id


def test_respects_interval(session, monkeypatch):
    monkeypatch.setattr(
        "app.scheduler.run_check", fake_checker(CheckOutcome(ok=True, latency_ms=5))
    )
    target = make_target(session, interval_seconds=60)
    last_run: dict[int, datetime] = {}
    now = datetime.now(timezone.utc)

    first = run_due_checks(session, last_run, now)
    too_soon = run_due_checks(session, last_run, now + timedelta(seconds=10))
    in_time = run_due_checks(session, last_run, now + timedelta(seconds=61))

    assert (first, too_soon, in_time) == (1, 0, 1)
    assert len(session.scalars(select(CheckResult)).all()) == 2
    assert last_run[target.id] == now + timedelta(seconds=61)


def test_stores_successful_result(session, monkeypatch):
    monkeypatch.setattr(
        "app.scheduler.run_check",
        fake_checker(CheckOutcome(ok=True, latency_ms=42, status_code=200)),
    )
    make_target(session)
    now = datetime.now(timezone.utc)

    run_due_checks(session, {}, now)

    result = session.scalars(select(CheckResult)).one()
    assert result.ok is True
    assert result.latency_ms == 42
    assert result.status_code == 200
    assert result.error is None
    assert result.checked_at.replace(tzinfo=timezone.utc) == now


def test_stores_failed_result(session, monkeypatch):
    monkeypatch.setattr(
        "app.scheduler.run_check",
        fake_checker(CheckOutcome(ok=False, error="Таймаут: 5 с")),
    )
    make_target(session)

    run_due_checks(session, {}, datetime.now(timezone.utc))

    result = session.scalars(select(CheckResult)).one()
    assert result.ok is False
    assert result.error == "Таймаут: 5 с"


def test_cleanup_removes_only_old_results(session):
    target = make_target(session)
    now = datetime.now(timezone.utc)
    session.add_all(
        [
            CheckResult(
                target_id=target.id,
                checked_at=now - timedelta(days=40),
                ok=True,
            ),
            CheckResult(
                target_id=target.id,
                checked_at=now - timedelta(days=1),
                ok=True,
            ),
        ]
    )
    session.commit()

    deleted = cleanup_old_results(session, days=30, now=now)

    remaining = session.scalars(select(CheckResult)).all()
    assert deleted == 1
    assert len(remaining) == 1


def test_scheduler_start_and_stop(monkeypatch):
    scheduler = Scheduler(tick_seconds=1)
    monkeypatch.setattr(scheduler, "tick", lambda: 0)

    scheduler.start()
    assert scheduler.is_running is True

    scheduler.stop()
    assert scheduler.is_running is False


def test_scheduler_tick_uses_database(session, monkeypatch):
    monkeypatch.setattr(
        "app.scheduler.run_check", fake_checker(CheckOutcome(ok=True, latency_ms=3))
    )
    monkeypatch.setattr("app.scheduler.SessionLocal", TestingSessionLocal)
    make_target(session)
    scheduler = Scheduler()

    checked = scheduler.tick()

    assert checked == 1
    assert len(session.scalars(select(CheckResult)).all()) == 1


def test_target_deleted_during_check_does_not_break_scheduler(session, monkeypatch):
    target = make_target(session)
    other_session = TestingSessionLocal()

    def checker_that_deletes_target(target_type, config, timeout=5):
        # Имитируем удаление цели через API прямо во время её проверки
        other_session.execute(delete(Target).where(Target.id == target.id))
        other_session.commit()
        return CheckOutcome(ok=True, latency_ms=1)

    monkeypatch.setattr("app.scheduler.run_check", checker_that_deletes_target)

    try:
        checked = run_due_checks(session, {}, datetime.now(timezone.utc))
    finally:
        other_session.close()

    assert checked == 0
    assert session.scalars(select(CheckResult)).all() == []


def test_other_targets_are_checked_after_one_is_deleted_mid_check(session, monkeypatch):
    first = make_target(session, name="Первый", config={"url": "https://first.example"})
    second = make_target(
        session, name="Второй", config={"url": "https://second.example"}
    )
    other_session = TestingSessionLocal()

    def checker(target_type, config, timeout=5):
        # Первую цель «удаляют» прямо во время её проверки
        if config["url"] == "https://first.example":
            other_session.execute(delete(Target).where(Target.id == first.id))
            other_session.commit()
        return CheckOutcome(ok=True, latency_ms=1)

    monkeypatch.setattr("app.scheduler.run_check", checker)

    try:
        checked = run_due_checks(session, {}, datetime.now(timezone.utc))
    finally:
        other_session.close()

    results = session.scalars(select(CheckResult)).all()
    assert checked == 1
    assert [result.target_id for result in results] == [second.id]
