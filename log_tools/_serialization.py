from __future__ import annotations

import re
from typing import Any

from .collector import LogEntry


def serialize_entry(entry: LogEntry) -> dict[str, Any]:
    """Сериализует ``LogEntry`` в словарь для JSON и хранения.

    Args:
        entry: Запись лога.

    Returns:
        Словарь с полями записи.
    """
    data = dict(entry.data)
    if entry.type.value == "sql" and "sql" in data:
        data["sql"] = format_sql(data.get("sql", ""), data.get("params"))
    return {
        "type": entry.type.value,
        "timestamp": entry.timestamp,
        "duration_ms": entry.duration_ms,
        "is_slow": entry.is_slow,
        "data": data,
    }


def format_sql(sql: str, params: Any = None) -> str:
    """Форматирует SQL-запрос и подставляет параметры inline.

    Заменяет ``?`` на реальные значения из ``params``.
    Затем форматирует через ``sqlparse``.

    Args:
        sql: Текст SQL-запроса.
        params: Параметры запроса (список, кортеж или dict).

    Returns:
        Отформатированный SQL-запрос с подставленными параметрами.
    """
    if params:
        sql = _substitute_params(sql, params)

    try:
        import sqlparse

        formatted = sqlparse.format(
            sql,
            reindent=True,
            keyword_case="upper",
        )
    except ImportError:
        formatted = sql

    return formatted


def _substitute_params(sql: str, params: Any) -> str:
    """Подставляет параметры в SQL-запрос.

    Поддерживает:
    - ``?`` плейсхолдеры (SQLite, MySQL)
    - ``%s`` плейсхолдеры (PostgreSQL)
    - Позиционные параметры (список/кортеж)
    - Именованные параметры (dict с ``%(name)s``)

    Args:
        sql: SQL-запрос с плейсхолдерами.
        params: Значения параметров.

    Returns:
        SQL-запрос с подставленными значениями.
    """
    if isinstance(params, dict):
        for key, value in params.items():
            sql = sql.replace(f"%({key})s", _quote(value))
        return sql

    if isinstance(params, (list, tuple)):
        # ? плейсхолдеры
        if "?" in sql:
            for value in params:
                sql = sql.replace("?", _quote(value), 1)
            return sql

        # %s плейсхолдеры
        if "%s" in sql:
            for value in params:
                sql = sql.replace("%s", _quote(value), 1)
            return sql

    return sql


def _quote(value: Any) -> str:
    """Форматирует значение SQL-параметра для подстановки в запрос.

    Args:
        value: Значение параметра.

    Returns:
        Строковое представление значения, безопасное для SQL.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, bytes):
        return f"X'{value.hex()}'"
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def normalize_sql(sql: str) -> str:
    """Нормализует SQL-запрос для сравнения.

    Заменяет параметры на плейсхолдеры, приводит к нижнему регистру,
    убирает лишние пробелы. Используется для группировки дублирующихся запросов.

    Args:
        sql: Текст SQL-запроса.

    Returns:
        Нормализованный SQL-запрос.
    """
    normalized = sql
    normalized = re.sub(r"'[^']*'", "?", normalized)
    normalized = re.sub(r"\d+\.?\d*", "?", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = normalized.lower()
    return normalized

