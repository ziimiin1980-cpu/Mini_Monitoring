import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from fastapi import Depends, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import router as api_router
from app.api import status_router
from app.config import PROJECT_ROOT, settings
from app.db import get_db
from app.messages import error_details
from app.pages import BASE_DIR
from app.pages import router as pages_router
from app.scheduler import scheduler

logger = logging.getLogger(__name__)

LOG_FILE = PROJECT_ROOT / "logs" / "app.log"
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 5

# Для этих путей ошибки отдаём в JSON, для остальных — простой HTML
JSON_ERROR_PREFIXES = ("/api", "/health", "/docs", "/redoc", "/openapi.json", "/static")


def _configure_logging() -> None:
    """Логи пишем и в консоль, и в файл с ротацией (5 файлов по 1 МБ)."""
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())

    if not any(isinstance(handler, RotatingFileHandler) for handler in root.handlers):
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    if not any(handler.__class__ is logging.StreamHandler for handler in root.handlers):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)

    # httpx пишет INFO на каждый запрос — при частых проверках это засоряет журнал
    logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Готовит логи и запускает планировщик вместе с приложением."""
    _configure_logging()
    logger.info("Приложение запускается")
    scheduler.start()
    try:
        yield
    finally:
        scheduler.stop()
        logger.info("Приложение остановлено")


app = FastAPI(title="Mini Monitoring", version="0.1.0", lifespan=lifespan)
app.include_router(api_router)
app.include_router(status_router)
app.include_router(pages_router)

# Статические файлы (CSS и JavaScript) дашборда
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Отдаёт ошибки валидации с понятными русскими текстами."""
    return JSONResponse(
        status_code=422,
        content={"detail": error_details(exc.errors())},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> Response:
    """Ловит непредвиденные ошибки: подробности — в лог, пользователю — понятный ответ."""
    logger.exception(
        "Необработанная ошибка при обработке %s %s", request.method, request.url.path
    )

    if request.url.path.startswith(JSON_ERROR_PREFIXES):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Внутренняя ошибка сервера"},
        )

    return HTMLResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=(
            "<!DOCTYPE html><html lang='ru'><head><meta charset='utf-8'>"
            "<title>Ошибка</title></head><body>"
            "<h1>Внутренняя ошибка сервера</h1>"
            "<p>Подробности записаны в журнал <code>logs/app.log</code>.</p>"
            "<p><a href='/'>Вернуться на дашборд</a></p>"
            "</body></html>"
        ),
    )


@app.get("/health", response_class=JSONResponse)
def health(db: Session = Depends(get_db)) -> JSONResponse:
    """Проверка, что приложение запущено и база данных доступна."""
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        # Любая ошибка при обращении к БД означает, что приложение работает
        # не полностью: сообщаем об этом кодом 503 и понятным телом ответа.
        # В лог пишем только текст ошибки — полный traceback здесь бесполезен
        # и засоряет журнал при каждой проверке.
        logger.warning("Проверка /health: база данных недоступна (%s)", exc)
        return JSONResponse(
            status_code=503,
            content={"status": "error", "database": "unavailable"},
        )

    return JSONResponse(
        status_code=200,
        content={"status": "ok", "database": "ok"},
    )
