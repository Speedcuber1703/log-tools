"""Сериализация и нормализация лог-записей.

Предоставляет функции для сериализации ``LogEntry``, нормализации SQL
и обнаружения N+1 паттернов.
"""
from __future__ import annotations

import re
from typing import Any

from .collector import EntryType, LogEntry

# Предкомпилированные regex-паттерны
_RE_STRING = re.compile(r"'[^']*'")
_RE_NUMBER = re.compile(r"\b\d+\.?\d*\b")
_RE_PERCENT_S = re.compile(r"%s")
_RE_PLACEHOLDER = re.compile(r"\?")
_RE_WHITESPACE = re.compile(r"\s+")
_RE_FROM_TABLE = re.compile(r'from\s+"?([a-z_]+)"?')
_RE_WHERE_EQUALS = re.compile(r"where\s+.*=\s*\?")
_RE_WHERE_CLAUSE = re.compile(r"WHERE.*")


def serialize_entry(entry: LogEntry) -> dict[str, Any]:
    """Сериализует ``LogEntry`` в словарь для JSON.

    Args:
        entry: Запись лога.

    Returns:
        Словарь с полями записи.
    """
    data = dict(entry.data)
    if entry.type == EntryType.SQL:
        raw_sql = data.get("sql", "")
        data["sql"] = format_sql(raw_sql, data.get("params"))
        data["normalized_sql"] = normalize_sql(raw_sql)
    return {
        "type": entry.type.value,
        "timestamp": entry.timestamp,
        "duration_ms": entry.duration_ms,
        "is_slow": entry.is_slow,
        "data": data,
    }


def format_sql(sql: str, params: Any = None) -> str:
    """Форматирует SQL-запрос и подставляет параметры inline.

    Args:
        sql: Текст SQL-запроса.
        params: Параметры запроса.

    Returns:
        Отформатированный SQL.
    """
    if params:
        sql = _substitute_params(sql, params)

    try:
        import sqlparse
        formatted = sqlparse.format(sql, reindent=True, keyword_case="upper")
    except ImportError:
        formatted = sql

    return formatted


def normalize_sql(sql: str) -> str:
    """Нормализует SQL-запрос для сравнения.

    Заменяет параметры на ``?``, приводит к нижнему регистру,
    убирает лишние пробелы.

    Args:
        sql: Текст SQL-запроса.

    Returns:
        Нормализованный SQL.
    """
    normalized = _RE_STRING.sub("?", sql)
    normalized = _RE_NUMBER.sub("?", normalized)
    normalized = _RE_PERCENT_S.sub("?", normalized)
    normalized = _RE_PLACEHOLDER.sub("?", normalized)
    normalized = _RE_WHITESPACE.sub(" ", normalized).strip()
    return normalized.lower()


def detect_n_plus_one(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Обнаруживает N+1 паттерны в SQL-запросах.

    N+1 — это когда один запрос получает список объектов,
    а затем для каждого объекта делается отдельный запрос.

    Args:
        entries: Список записей лога.

    Returns:
        Список обнаруженных N+1 паттернов.
    """
    sql_entries = [e for e in entries if e.get("type") == EntryType.SQL.value]
    if len(sql_entries) < 2:
        return []

    patterns: dict[str, dict[str, Any]] = {}
    for entry in sql_entries:
        sql = entry.get("data", {}).get("sql", "")
        normalized = entry.get("data", {}).get("normalized_sql", "")
        duration = entry.get("duration_ms") or 0

        table_match = _RE_FROM_TABLE.search(normalized)
        if not table_match:
            continue
        table = table_match.group(1)

        if not _RE_WHERE_EQUALS.search(normalized):
            continue

        base_query = _RE_WHERE_CLAUSE.sub("WHERE ?", normalized)

        if table not in patterns:
            patterns[table] = {}
        if base_query not in patterns[table]:
            patterns[table][base_query] = {"count": 0, "total_ms": 0.0, "sql": sql}
        patterns[table][base_query]["count"] += 1
        patterns[table][base_query]["total_ms"] += duration

    results: list[dict[str, Any]] = []
    for table, queries in patterns.items():
        for info in queries.values():
            if info["count"] >= 3:
                results.append({
                    "table": table,
                    "count": info["count"],
                    "total_ms": round(info["total_ms"], 2),
                    "sql": info["sql"],
                })

    results.sort(key=lambda x: x["count"], reverse=True)
    return results


def _substitute_params(sql: str, params: Any) -> str:
    """Подставляет параметры в SQL-запрос.

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
        values = [_quote(v) for v in params]
        # Try ? placeholders first
        if "?" in sql:
            parts = sql.split("?", len(values))
            return "".join(p + v for p, v in zip(parts, values + [""] * max(0, len(parts) - len(values))))
        # Try %s placeholders
        if "%s" in sql:
            parts = sql.split("%s", len(values))
            return "".join(p + v for p, v in zip(parts, values + [""] * max(0, len(parts) - len(values))))

    return sql


def _quote(value: Any) -> str:
    """Форматирует значение SQL-параметра.

    Args:
        value: Значение параметра.

    Returns:
        Строковое представление для SQL.
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
