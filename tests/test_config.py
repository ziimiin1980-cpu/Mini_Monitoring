from app import scheduler
from app.config import PROJECT_ROOT, Settings, settings


def test_project_root_is_real_project_directory():
    assert (PROJECT_ROOT / "app").is_dir()
    assert (PROJECT_ROOT / ".env.example").is_file()


def test_settings_have_expected_defaults():
    fresh = Settings(database_url="postgresql+psycopg://user:pass@localhost/db")

    assert fresh.check_tick_seconds == 5
    assert fresh.retention_days == 30
    assert fresh.log_level == "INFO"


def test_settings_can_be_overridden_by_environment(monkeypatch):
    monkeypatch.setenv("CHECK_TICK_SECONDS", "15")
    monkeypatch.setenv("RETENTION_DAYS", "7")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    fresh = Settings(database_url="postgresql+psycopg://user:pass@localhost/db")

    assert fresh.check_tick_seconds == 15
    assert fresh.retention_days == 7
    assert fresh.log_level == "DEBUG"


def test_scheduler_constants_follow_settings():
    assert scheduler.CHECK_TICK_SECONDS == settings.check_tick_seconds
    assert scheduler.RETENTION_DAYS == settings.retention_days
