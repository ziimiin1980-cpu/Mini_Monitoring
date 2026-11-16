from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения. Значения читаются из файла .env в корне проекта."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Строка подключения к PostgreSQL, например:
    # postgresql+psycopg://postgres:пароль@localhost:5432/mini_monitoring
    database_url: str


settings = Settings()
