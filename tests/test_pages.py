from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import CheckResult

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


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
    yield TestClient(app, base_url="http://127.0.0.1")
    app.dependency_overrides.clear()


def make_target(client, name="Сайт компании"):
    response = client.post(
        "/api/targets",
        json={
            "name": name,
            "type": "http",
            "config": {"url": "https://example.com"},
        },
    )
    assert response.status_code == 201
    return response.json()


def test_dashboard_page_renders(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Mini Monitoring" in response.text
    assert "/static/app.js" in response.text


def test_dashboard_shows_empty_hint_without_targets(client):
    assert "Целей пока нет" in client.get("/").text


def test_target_page_shows_details_and_history(client, session):
    target = make_target(client)
    session.add(
        CheckResult(
            target_id=target["id"],
            checked_at=datetime.now(UTC),
            ok=False,
            latency_ms=5000,
            error="Таймаут: 5 с",
        )
    )
    session.commit()

    response = client.get(f"/targets/{target['id']}")

    assert response.status_code == 200
    assert "Сайт компании" in response.text
    assert "https://example.com" in response.text
    assert "Таймаут: 5 с" in response.text
    assert "ошибка" in response.text


def test_target_page_without_history(client):
    target = make_target(client)

    response = client.get(f"/targets/{target['id']}")

    assert response.status_code == 200
    assert "Проверок ещё не было" in response.text


def test_unknown_target_page_returns_404(client):
    assert client.get("/targets/99999").status_code == 404


def test_static_css_is_served(client):
    response = client.get("/static/style.css")

    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]


def test_swagger_docs_still_available(client):
    assert client.get("/docs").status_code == 200
