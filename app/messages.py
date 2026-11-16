"""Перевод сообщений валидации Pydantic на понятный русский язык."""

from typing import Any

# Типовые машинные сообщения Pydantic -> человеческий текст.
# Полный список типов: https://docs.pydantic.dev/latest/errors/validation_errors/
SIMPLIFIED_MESSAGES: dict[str, str] = {
    "missing": "обязательное поле",
    "int_parsing": "должно быть целым числом",
    "int_type": "должно быть целым числом",
    "float_parsing": "должно быть числом",
    "float_type": "должно быть числом",
    "bool_parsing": "должно быть true или false",
    "bool_type": "должно быть true или false",
    "string_type": "должно быть строкой",
    "string_too_short": "слишком короткое значение",
    "string_too_long": "слишком длинное значение",
    "url_parsing": "неверный адрес",
    "url_scheme": "адрес должен начинаться с http:// или https://",
    "url_too_long": "слишком длинный адрес",
    "json_invalid": "некорректный JSON в теле запроса",
    "literal_error": "недопустимое значение",
    "extra_forbidden": "лишнее поле, которого нет в схеме",
    "greater_than_equal": "значение меньше допустимого",
    "less_than_equal": "значение больше допустимого",
}


def _field_name(location: tuple[Any, ...] | list[Any]) -> str:
    """Превращает ('body', 'config') в 'config', убирая служебный префикс."""
    parts = [str(part) for part in location]
    if parts and parts[0] in {"body", "query", "path", "header", "cookie"}:
        parts = parts[1:]
    return ".".join(parts)


def _translate(error: dict[str, Any]) -> str:
    """Понятный текст одной ошибки валидации."""
    error_type = str(error.get("type", ""))
    context = error.get("ctx") or {}

    # Наши собственные проверки уже пишут сообщения по-русски
    if error_type == "value_error":
        message = str(error.get("msg", "некорректное значение"))
        prefix = "Value error, "
        return message[len(prefix) :] if message.startswith(prefix) else message

    if error_type == "less_than_equal" and "le" in context:
        return f"значение должно быть не больше {context['le']}"
    if error_type == "greater_than_equal" and "ge" in context:
        return f"значение должно быть не меньше {context['ge']}"
    if error_type == "string_too_short" and "min_length" in context:
        return f"слишком короткое значение (минимум {context['min_length']})"
    if error_type == "string_too_long" and "max_length" in context:
        return f"слишком длинное значение (максимум {context['max_length']})"
    if error_type == "literal_error" and "expected" in context:
        return f"допустимые значения: {context['expected']}"

    return SIMPLIFIED_MESSAGES.get(error_type, str(error.get("msg", "некорректное значение")))


def error_details(errors: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Список ошибок для JSON-ответа API."""
    return [
        {"field": _field_name(error.get("loc", ())), "message": _translate(error)}
        for error in errors
    ]


def format_errors(errors: list[dict[str, Any]]) -> str:
    """Одна строка с ошибками — для HTML-форм."""
    parts = []
    for error in errors:
        field = _field_name(error.get("loc", ()))
        message = _translate(error)
        parts.append(f"{field}: {message}" if field else message)
    return "; ".join(parts) or "некорректные данные"
