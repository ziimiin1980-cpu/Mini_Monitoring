import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app

# Тестовая база: SQLite в памяти. PostgreSQL для тестов не нужен,
# а данные каждого теста живут только внутри одного теста.
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
    yield TestClient(app, base_url="http://127.0.0.1")

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def make_payload(**overrides):
    payload = {
        "name": "Сайт компании",
        "type": "http",
        "config": {"url": "https://example.com"},
    }
    payload.update(overrides)
    return payload


def test_create_http_target_applies_defaults(client):
    response = client.post("/api/targets", json=make_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["name"] == "Сайт компании"
    assert body["type"] == "http"
    assert body["config"] == {
        "url": "https://example.com/",
        "method": "GET",
        "expected_status": 200,
        "accept_any_status": False,
    }
    assert body["interval_seconds"] == 60
    assert body["timeout_seconds"] == 5
    assert body["enabled"] is True
    assert body["created_at"] and body["updated_at"]


def test_create_http_target_with_any_status(client):
    response = client.post(
        "/api/targets",
        json=make_payload(config={"url": "https://example.com", "accept_any_status": True}),
    )

    assert response.status_code == 201
    assert response.json()["config"] == {
        "url": "https://example.com/",
        "method": "GET",
        "expected_status": 200,
        "accept_any_status": True,
    }


def test_create_tcp_and_process_targets(client):
    tcp = client.post(
        "/api/targets",
        json=make_payload(name="Роутер", type="tcp", config={"host": "192.168.1.1", "port": 443}),
    )
    process = client.post(
        "/api/targets",
        json=make_payload(name="Nginx", type="process", config={"name": "nginx.exe"}),
    )

    assert tcp.status_code == 201
    assert tcp.json()["config"] == {"host": "192.168.1.1", "port": 443}
    assert process.status_code == 201
    assert process.json()["config"] == {"name": "nginx.exe"}


def test_create_duplicate_name_returns_409(client):
    assert client.post("/api/targets", json=make_payload()).status_code == 201

    response = client.post("/api/targets", json=make_payload())

    assert response.status_code == 409
    assert "уже существует" in response.json()["detail"]


def test_create_unknown_type_returns_422(client):
    response = client.post("/api/targets", json=make_payload(type="ftp"))

    assert response.status_code == 422


def test_create_http_without_url_returns_422(client):
    response = client.post("/api/targets", json=make_payload(config={}))

    assert response.status_code == 422
    assert "url" in str(response.json()["detail"])


def test_create_tcp_with_bad_port_returns_422(client):
    response = client.post(
        "/api/targets",
        json=make_payload(name="Хост", type="tcp", config={"host": "a", "port": 70000}),
    )

    assert response.status_code == 422
    assert "port" in str(response.json()["detail"])


def test_create_with_unknown_config_key_returns_422(client):
    response = client.post(
        "/api/targets",
        json=make_payload(name="Хост", type="tcp", config={"host": "a", "port": 80, "portt": 80}),
    )

    assert response.status_code == 422


def test_create_with_empty_name_returns_422(client):
    response = client.post("/api/targets", json=make_payload(name=""))

    assert response.status_code == 422


def test_list_targets_returns_created_items(client):
    client.post("/api/targets", json=make_payload())
    client.post(
        "/api/targets",
        json=make_payload(name="Роутер", type="tcp", config={"host": "10.0.0.1", "port": 22}),
    )

    response = client.get("/api/targets")

    assert response.status_code == 200
    names = [item["name"] for item in response.json()]
    assert names == ["Сайт компании", "Роутер"]


def test_get_target_by_id_and_404_for_unknown(client):
    created = client.post("/api/targets", json=make_payload()).json()

    found = client.get(f"/api/targets/{created['id']}")
    missing = client.get("/api/targets/99999")

    assert found.status_code == 200
    assert found.json()["id"] == created["id"]
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Цель не найдена"


def test_update_target_replaces_fields(client):
    created = client.post("/api/targets", json=make_payload()).json()

    response = client.put(
        f"/api/targets/{created['id']}",
        json=make_payload(
            name="Новое имя",
            type="tcp",
            config={"host": "example.org", "port": 8080},
            interval_seconds=120,
            timeout_seconds=10,
            enabled=False,
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Новое имя"
    assert body["type"] == "tcp"
    assert body["config"] == {"host": "example.org", "port": 8080}
    assert body["interval_seconds"] == 120
    assert body["timeout_seconds"] == 10
    assert body["enabled"] is False

    # изменение действительно сохранено
    assert client.get(f"/api/targets/{created['id']}").json()["name"] == "Новое имя"


def test_update_unknown_target_returns_404(client):
    response = client.put("/api/targets/99999", json=make_payload())

    assert response.status_code == 404


def test_update_to_duplicate_name_returns_409(client):
    client.post("/api/targets", json=make_payload())
    second = client.post(
        "/api/targets",
        json=make_payload(name="Роутер", type="tcp", config={"host": "10.0.0.1", "port": 22}),
    ).json()

    response = client.put(f"/api/targets/{second['id']}", json=make_payload())

    assert response.status_code == 409


def test_delete_target(client):
    created = client.post("/api/targets", json=make_payload()).json()

    deleted = client.delete(f"/api/targets/{created['id']}")

    assert deleted.status_code == 204
    assert client.get(f"/api/targets/{created['id']}").status_code == 404
    assert client.get("/api/targets").json() == []


def test_delete_unknown_target_returns_404(client):
    response = client.delete("/api/targets/99999")

    assert response.status_code == 404
