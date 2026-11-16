import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def client():
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app, base_url="http://127.0.0.1")
    client.get("/")  # первый запрос выдаёт CSRF-cookie
    client.csrf = client.cookies.get("csrf_token")
    yield client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def target_payload(**overrides):
    payload = {
        "name": "Сайт",
        "type": "http",
        "config": {"url": "https://example.com"},
    }
    payload.update(overrides)
    return payload


def test_invalid_tcp_port_message_is_readable(client):
    response = client.post(
        "/api/targets",
        json=target_payload(name="Хост", type="tcp", config={"host": "a", "port": 70000}),
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert "не больше 65535" in detail[0]["message"]
    assert "tcp" in detail[0]["message"]


def test_missing_fields_are_reported_in_russian(client):
    response = client.post("/api/targets", json={})

    assert response.status_code == 422
    fields = {item["field"]: item["message"] for item in response.json()["detail"]}
    assert fields["name"] == "обязательное поле"
    assert fields["type"] == "обязательное поле"
    assert fields["config"] == "обязательное поле"


def test_unknown_type_lists_allowed_values(client):
    response = client.post("/api/targets", json=target_payload(type="ftp"))

    assert response.status_code == 422
    message = response.json()["detail"][0]["message"]
    assert "допустимые значения" in message
    assert "http" in message


def test_too_small_interval_message(client):
    response = client.post("/api/targets", json=target_payload(interval_seconds=1))

    assert response.status_code == 422
    message = response.json()["detail"][0]["message"]
    assert "не меньше 5" in message


def test_form_shows_readable_error(client):
    response = client.post(
        "/targets/new",
        data={
            "name": "Плохая",
            "type": "tcp",
            "host": "a",
            "port": "70000",
            "interval_seconds": "60",
            "timeout_seconds": "5",
            "csrf_token": client.csrf,
        },
    )

    assert response.status_code == 400
    assert "не больше 65535" in response.text


def boom() -> None:
    raise RuntimeError("тестовая поломка")


def test_unexpected_error_returns_json_for_api(client):
    app.add_api_route("/api/__boom", boom, methods=["GET"])
    client_without_raise = TestClient(
        app, raise_server_exceptions=False, base_url="http://127.0.0.1"
    )

    response = client_without_raise.get("/api/__boom")

    assert response.status_code == 500
    assert response.json() == {"detail": "Внутренняя ошибка сервера"}


def test_unexpected_error_returns_html_for_pages(client):
    app.add_api_route("/__boom-page", boom, methods=["GET"])
    client_without_raise = TestClient(
        app, raise_server_exceptions=False, base_url="http://127.0.0.1"
    )

    response = client_without_raise.get("/__boom-page")

    assert response.status_code == 500
    assert "text/html" in response.headers["content-type"]
    assert "Внутренняя ошибка сервера" in response.text
