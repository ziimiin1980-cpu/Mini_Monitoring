from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Корень проекта (каталог, где лежат app/, tests/, .env)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Настройки приложения.

    Значения читаются из файла .env в корне проекта: путь считается от файла
    модуля, поэтому приложение можно запускать из любого каталога.
    Переменные окружения имеют приоритет над файлом .env.
    """

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Строка подключения к PostgreSQL, например:
    # postgresql+psycopg://postgres:пароль@localhost:5432/mini_monitoring
    database_url: str

    # Как часто планировщик просыпается, секунды
    check_tick_seconds: int = 5

    # Сколько дней хранить историю проверок
    retention_days: int = 30

    # Уровень логирования: DEBUG, INFO, WARNING, ERROR
    log_level: str = "INFO"

    # Пароль для входа в интерфейс. Пусто — вход не требуется (локальный режим)
    app_password: str = ""

    # Секрет для подписи cookie сессии. Пусто — генерируется при старте
    # (после перезапуска приложения вход понадобится снова)
    session_secret: str = ""

    # Хосты, с которых разрешены запросы (защита от DNS-rebinding)
    allowed_hosts: str = "127.0.0.1,localhost,::1"


settings = Settings()
