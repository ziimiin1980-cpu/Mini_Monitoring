from fastapi import FastAPI

app = FastAPI(title="Mini Monitoring", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    """Проверка, что приложение запущено и отвечает."""
    return {"status": "ok"}
