from __future__ import annotations

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
    """Форматирует SQL-запрос и подставляет параметры.

    Использует ``sqlparse`` для форматирования. Если форматирование
    недоступно, возвращает исходный запрос.

    Args:
        sql: Текст SQL-запроса.
        params: Параметры запроса для подстановки.

    Returns:
        Отформатированный SQL-запрос.
    """
    try:
        import sqlparse

        formatted = sqlparse.format(
            sql,
            reindent=True,
            keyword_case="upper",
        )
    except ImportError:
        formatted = sql

    if params:
        formatted = f"{formatted}\n-- params: {params}"

    return formatted
