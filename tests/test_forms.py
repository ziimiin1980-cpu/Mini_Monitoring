import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Target

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
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


def form_data(**overrides):
    data = {
        "name": "Новый сайт",
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


def test_new_target_form_renders(client):
    response = client.get("/targets/new")

    assert response.status_code == 200
    assert 'name="name"' in response.text
    assert 'name="interval_seconds"' in response.text
    assert "Добавить цель" in response.text


def test_create_target_from_form(client, session):
    response = client.post("/targets/new", data=form_data())

    target = session.scalars(select(Target)).one()
    assert response.status_code == 303
    assert response.headers["location"] == f"/targets/{target.id}"
    assert target.name == "Новый сайт"
    assert target.config["url"] == "https://example.com/"
    assert target.enabled is True


def test_create_process_target_from_form(client, session):
    response = client.post(
        "/targets/new",
        data=form_data(
            name="Nginx", type="process", process_name="nginx.exe", enabled=None
        ),
    )

    target = session.scalars(select(Target)).one()
    assert response.status_code == 303
    assert target.config == {"name": "nginx.exe"}
    assert target.enabled is False


def test_create_target_with_invalid_port_shows_error(client, session):
    response = client.post(
        "/targets/new",
        data=form_data(name="Плохой", type="tcp", host="a", port="70000"),
    )

    assert response.status_code == 400
    assert "port" in response.text
    assert session.scalars(select(Target)).all() == []


def test_create_target_with_duplicate_name_shows_error(client, session):
    client.post("/targets/new", data=form_data())

    response = client.post("/targets/new", data=form_data())

    assert response.status_code == 400
    assert "уже существует" in response.text
    assert len(session.scalars(select(Target)).all()) == 1


def test_create_target_with_empty_name_shows_error(client):
    response = client.post("/targets/new", data=form_data(name=""))

    assert response.status_code == 400
    assert "Имя цели" in response.text or "name" in response.text


def test_create_target_with_any_status_mode(client, session):
    response = client.post("/targets/new", data=form_data(status_mode="any"))

    target = session.scalars(select(Target)).one()
    assert response.status_code == 303
    assert target.config["accept_any_status"] is True
    # expected_status остаётся в config по умолчанию, но в этом режиме не используется
    assert target.config["expected_status"] == 200


def test_edit_form_preselects_any_status_mode(client):
    client.post("/targets/new", data=form_data(status_mode="any"))
    target = client.get("/api/targets").json()[0]

    response = client.get(f"/targets/{target['id']}/edit")

    assert response.status_code == 200
    assert 'value="any" selected' in response.text


def test_edit_form_is_prefilled(client):
    client.post("/targets/new", data=form_data())
    target = client.get("/api/targets").json()[0]

    response = client.get(f"/targets/{target['id']}/edit")

    assert response.status_code == 200
    assert 'value="Новый сайт"' in response.text
    assert 'value="https://example.com/"' in response.text


def test_update_target_from_form(client, session):
    client.post("/targets/new", data=form_data())
    target_id = client.get("/api/targets").json()[0]["id"]

    response = client.post(
        f"/targets/{target_id}/edit",
        data=form_data(
            name="Переименованный", type="tcp", host="10.0.0.1", port="22",
            interval_seconds="300",
        ),
    )

    session.expire_all()
    target = session.get(Target, target_id)
    assert response.status_code == 303
    assert response.headers["location"] == f"/targets/{target_id}"
    assert target.name == "Переименованный"
    assert target.type == "tcp"
    assert target.config == {"host": "10.0.0.1", "port": 22}
    assert target.interval_seconds == 300


def test_update_to_duplicate_name_shows_error(client, session):
    client.post("/targets/new", data=form_data(name="Первая"))
    client.post("/targets/new", data=form_data(name="Вторая"))
    target_id = client.get("/api/targets").json()[1]["id"]

    response = client.post(f"/targets/{target_id}/edit", data=form_data(name="Первая"))

    assert response.status_code == 400
    assert "уже существует" in response.text


def test_toggle_target(client, session):
    client.post("/targets/new", data=form_data())
    target_id = client.get("/api/targets").json()[0]["id"]

    first = client.post(f"/targets/{target_id}/toggle", data={"next": f"/targets/{target_id}"})
    session.expire_all()
    assert client.get(f"/api/targets/{target_id}").json()["enabled"] is False

    second = client.post(f"/targets/{target_id}/toggle", data={"next": "/"})
    assert client.get(f"/api/targets/{target_id}").json()["enabled"] is True

    assert first.status_code == 303
    assert first.headers["location"] == f"/targets/{target_id}"
    assert second.status_code == 303
    assert second.headers["location"] == "/"


def test_toggle_rejects_external_redirect(client):
    client.post("/targets/new", data=form_data())
    target_id = client.get("/api/targets").json()[0]["id"]

    response = client.post(
        f"/targets/{target_id}/toggle", data={"next": "https://evil.example"}
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_delete_target_from_form(client, session):
    client.post("/targets/new", data=form_data())
    target_id = client.get("/api/targets").json()[0]["id"]

    response = client.post(f"/targets/{target_id}/delete")

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert session.scalars(select(Target)).all() == []


def test_edit_form_for_unknown_target_returns_404(client):
    assert client.get("/targets/99999/edit").status_code == 404
