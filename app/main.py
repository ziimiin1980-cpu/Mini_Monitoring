import logging

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db

logger = logging.getLogger(__name__)

app = FastAPI(title="Mini Monitoring", version="0.1.0")


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
