from typing import Any

import psutil

from app.checks.base import CheckOutcome


def check_process(config: dict[str, Any], timeout: float = 5) -> CheckOutcome:
    """Проверяет, что на этой машине запущен процесс с указанным именем.

    timeout не используется: проверка списка процессов мгновенная.
    Параметр нужен, чтобы у всех проверок был одинаковый интерфейс.
    """
    name = str(config.get("name", "")).strip()
    if not name:
        return CheckOutcome(ok=False, error="В параметрах проверки не указано имя процесса")

    wanted = name.lower()
    try:
        for proc in psutil.process_iter(["name"]):
            current = (proc.info.get("name") or "").lower()
            if current == wanted:
                return CheckOutcome(ok=True, details={"name": name, "pid": proc.pid})
    except psutil.Error as exc:
        return CheckOutcome(ok=False, error=f"Ошибка чтения списка процессов: {exc}")

    return CheckOutcome(ok=False, error=f"Процесс '{name}' не найден")
