import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import router as api_router
from app.api import status_router
from app.db import get_db
from app.scheduler import scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
# httpx пишет INFO на каждый запрос — при частых проверках это засоряет журнал
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Запускает планировщик проверок вместе с приложением и останавливает при выключении."""
    scheduler.start()
    try:
        yield
    finally:
        scheduler.stop()


app = FastAPI(title="Mini Monitoring", version="0.1.0", lifespan=lifespan)
app.include_router(api_router)
app.include_router(status_router)


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
