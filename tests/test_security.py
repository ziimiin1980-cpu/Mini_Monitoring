import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import security
from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import Target

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture(autouse=True)
def clear_login_attempts():
    security._login_attempts.clear()
    yield
    security._login_attempts.clear()


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
    client = TestClient(app, follow_redirects=False, base_url="http://127.0.0.1")
    client.get("/")  # первый запрос выдаёт CSRF-cookie
    client.csrf = client.cookies.get("csrf_token")
    yield client
    app.dependency_overrides.clear()


def form_fields(**overrides):
    data = {
        "name": "Сайт",
        "type": "http",
        "url": "https://example.com",
        "expected_status": "200",
        "status_mode": "exact",
        "host": "",
        "port": "",
        "process_name": "",
        "interval_seconds": "60",
        "timeout_seconds": "5",
        "enabled": "true",
    }
    data.update(overrides)
    return data


def test_foreign_host_is_rejected():
    foreign = TestClient(app, base_url="http://evil.example")

    response = foreign.get("/health")

    assert response.status_code == 400


def test_security_headers_and_csrf_cookie():
    # Свежий клиент: первый ответ должен выдать CSRF-cookie и заголовки безопасности
    fresh = TestClient(app, base_url="http://127.0.0.1")

    response = fresh.get("/")

    assert response.status_code == 200
    assert "csrf_token=" in response.headers.get("set-cookie", "")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "same-origin"
    assert "Content-Security-Policy" in response.headers


def test_form_without_csrf_token_is_rejected(client, session):
    response = client.post("/targets/new", data=form_fields())

    assert response.status_code == 403
    assert session.scalars(select(Target)).all() == []


def test_form_with_csrf_token_is_accepted(client, session):
    response = client.post("/targets/new", data={**form_fields(), "csrf_token": client.csrf})

    assert response.status_code == 303
    assert len(session.scalars(select(Target)).all()) == 1


def test_password_protects_pages_and_api(client, monkeypatch):
    monkeypatch.setattr(settings, "app_password", "secret")

    page = client.get("/")
    api = client.get("/api/status")
    health = client.get("/health")

    assert page.status_code == 303
    assert page.headers["location"] == "/login"
    assert api.status_code == 401
    # health остаётся доступным: за ним следят внешние системы
    assert health.status_code == 200


def test_login_flow(client, monkeypatch):
    monkeypatch.setattr(settings, "app_password", "secret")

    wrong = client.post("/login", data={"password": "bad", "csrf_token": client.csrf})
    ok = client.post("/login", data={"password": "secret", "csrf_token": client.csrf})
    after_login = client.get("/")
    logout = client.post("/logout", data={"csrf_token": client.csrf})
    after_logout = client.get("/")

    assert wrong.status_code == 401
    assert "Неверный пароль" in wrong.text
    assert ok.status_code == 303
    assert ok.headers["location"] == "/"
    assert after_login.status_code == 200
    assert logout.status_code == 303
    assert logout.headers["location"] == "/login"
    assert after_logout.status_code == 303
    assert after_logout.headers["location"] == "/login"


def test_login_attempts_are_limited(client, monkeypatch):
    monkeypatch.setattr(settings, "app_password", "secret")

    statuses = [
        client.post("/login", data={"password": "bad", "csrf_token": client.csrf}).status_code
        for _ in range(security.LOGIN_ATTEMPTS_LIMIT)
    ]
    blocked = client.post("/login", data={"password": "bad", "csrf_token": client.csrf})

    assert statuses == [401] * security.LOGIN_ATTEMPTS_LIMIT
    assert blocked.status_code == 429


def test_without_password_app_is_open(client):
    assert client.get("/").status_code == 200
    assert client.get("/api/status").status_code == 200
