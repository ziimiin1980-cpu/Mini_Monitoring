from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.checks.base import CheckOutcome
from app.db import Base, get_db
from app.main import app
from app.models import CheckResult

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
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


@pytest.fixture
def client(session):
    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def make_target(client, name="Сайт", enabled=True):
    response = client.post(
        "/api/targets",
        json={
            "name": name,
            "type": "http",
            "config": {"url": "https://example.com"},
            "enabled": enabled,
        },
    )
    assert response.status_code == 201
    return response.json()


def add_result(session, target_id, when, ok=True, latency_ms=10, error=None):
    result = CheckResult(
        target_id=target_id,
        checked_at=when,
        ok=ok,
        latency_ms=latency_ms,
        error=error,
    )
    session.add(result)
    session.commit()
    return result


def test_status_without_checks(client):
    make_target(client)

    response = client.get("/api/status")

    assert response.status_code == 200
    item = response.json()[0]
    assert item["name"] == "Сайт"
    assert item["last_check"] is None
    assert item["uptime_24h"] is None
    assert item["checks_24h"] == 0


def test_status_counts_uptime_and_last_check(client, session):
    target = make_target(client)
    now = datetime.now(timezone.utc)
    add_result(session, target["id"], now - timedelta(hours=4), ok=True)
    add_result(session, target["id"], now - timedelta(hours=3), ok=True)
    add_result(session, target["id"], now - timedelta(hours=2), ok=True)
    add_result(
        session,
        target["id"],
        now - timedelta(hours=1),
        ok=False,
        latency_ms=5000,
        error="Таймаут: 5 с",
    )

    item = client.get("/api/status").json()[0]

    assert item["checks_24h"] == 4
    assert item["uptime_24h"] == 75.0
    assert item["last_check"]["ok"] is False
    assert item["last_check"]["error"] == "Таймаут: 5 с"


def test_status_ignores_checks_older_than_24h(client, session):
    target = make_target(client)
    now = datetime.now(timezone.utc)
    add_result(session, target["id"], now - timedelta(hours=30), ok=False)
    add_result(session, target["id"], now - timedelta(hours=1), ok=True)

    item = client.get("/api/status").json()[0]

    assert item["checks_24h"] == 1
    assert item["uptime_24h"] == 100.0
    assert item["last_check"]["ok"] is True


def test_status_includes_disabled_targets(client):
    make_target(client, name="Выключенная", enabled=False)

    item = client.get("/api/status").json()[0]

    assert item["name"] == "Выключенная"
    assert item["enabled"] is False


def test_history_returns_newest_first_with_limit(client, session):
    target = make_target(client)
    now = datetime.now(timezone.utc)
    for index in range(1, 6):
        add_result(
            session,
            target["id"],
            now - timedelta(minutes=10 - index),
            latency_ms=index,
        )

    response = client.get(f"/api/targets/{target['id']}/history", params={"limit": 3})

    assert response.status_code == 200
    assert [item["latency_ms"] for item in response.json()] == [5, 4, 3]


def test_history_for_unknown_target_returns_404(client):
    response = client.get("/api/targets/99999/history")

    assert response.status_code == 404


def test_manual_check_saves_result(client, monkeypatch):
    target = make_target(client)
    monkeypatch.setattr(
        "app.api.run_check",
        lambda target_type, config, timeout=5: CheckOutcome(
            ok=False, latency_ms=5000, error="Таймаут: 5 с"
        ),
    )

    response = client.post(f"/api/targets/{target['id']}/check")

    assert response.status_code == 201
    created = response.json()
    assert created["ok"] is False
    assert created["error"] == "Таймаут: 5 с"

    history = client.get(f"/api/targets/{target['id']}/history").json()
    status_item = client.get("/api/status").json()[0]
    assert len(history) == 1
    assert status_item["last_check"]["ok"] is False
    assert status_item["checks_24h"] == 1


def test_manual_check_for_unknown_target_returns_404(client):
    response = client.post("/api/targets/99999/check")

    assert response.status_code == 404
