from typing import Any

from app.checks.base import CheckOutcome
from app.checks.http import check_http
from app.checks.process import check_process
from app.checks.tcp import check_tcp

# Соответствие «тип цели из базы» → функция проверки
CHECKERS = {
    "http": check_http,
    "tcp": check_tcp,
    "process": check_process,
}


def run_check(
    target_type: str, config: dict[str, Any], timeout: float = 5
) -> CheckOutcome:
    """Выполняет проверку нужного типа.

    Никогда не выбрасывает исключения: любая проблема возвращается как
    CheckOutcome(ok=False, error=...), иначе одна «плохая» цель могла бы
    остановить весь планировщик.
    """
    checker = CHECKERS.get(target_type)
    if checker is None:
        return CheckOutcome(ok=False, error=f"Неизвестный тип проверки: {target_type}")

    try:
        return checker(config, timeout)
    except Exception as exc:  # последняя страховка на случай неожиданных ошибок
        return CheckOutcome(ok=False, error=f"Непредвиденная ошибка проверки: {exc}")
