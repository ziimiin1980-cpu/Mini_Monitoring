import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db import get_db
from app.main import app


class FakeSession:
    """Заглушка сессии БД: база отвечает нормально."""

    def execute(self, *args, **kwargs):
        return 1


class BrokenSession:
    """Заглушка сессии БД: база недоступна."""

    def execute(self, *args, **kwargs):
        raise OperationalError("SELECT 1", {}, ConnectionError("connection refused"))


def _override_db(session):
    """Подменяет настоящую сессию БД на заглушку — тесты не зависят от PostgreSQL."""

    def dependency():
        yield session

    return dependency


@pytest.fixture
def client_db_ok():
    app.dependency_overrides[get_db] = _override_db(FakeSession())
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def client_db_down():
    app.dependency_overrides[get_db] = _override_db(BrokenSession())
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_returns_ok(client_db_ok):
    response = client_db_ok.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_reports_database_problem(client_db_down):
    response = client_db_down.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "unavailable"}
