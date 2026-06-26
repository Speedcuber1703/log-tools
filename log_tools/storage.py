"""In-memory хранилище логов для одного процесса.

Используется по умолчанию для HTTP-запросов.
Логи хранятся в ``deque`` с ограниченным размером (кольцевой буфер).
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .collector import EntryType, Source


@dataclass
class RequestLog:
    """Сохранённый лог одного HTTP-запроса.

    Attributes:
        method: HTTP-метод.
        path: Путь запроса.
        status_code: HTTP-статус.
        elapsed_ms: Время выполнения в миллисекундах.
        timestamp: Unix-таймстемп.
        summary: Сводка из ``Collector.summary()``.
        entries: Список сериализованных записей.
        source: Источник логов.
        command_name: Имя management-команды.
    """

    method: str
    path: str
    status_code: int
    elapsed_ms: float
    timestamp: float = field(default_factory=time.time)
    summary: dict[str, Any] = field(default_factory=dict)
    entries: list[dict[str, Any]] = field(default_factory=list)
    source: Source = Source.HTTP
    command_name: str | None = None


class LogStorage:
    """In-memory хранилище логов (кольцевой буфер).

    Потокобезопасно через ``threading.Lock``.

    Attributes:
        max_size: Максимальное количество хранимых логов.
    """

    def __init__(self, max_size: int = 100) -> None:
        self.max_size: int = max_size
        self._logs: deque[RequestLog] = deque(maxlen=max_size)
        self._lock: threading.Lock = threading.Lock()

    def add(self, log: RequestLog) -> None:
        """Сохраняет лог запроса.

        Args:
            log: Лог запроса для сохранения.
        """
        with self._lock:
            self._logs.append(log)

    def all(self, limit: int | None = None) -> list[RequestLog]:
        """Возвращает сохранённые логи.

        Args:
            limit: Максимальное количество. ``None`` — все.

        Returns:
            Список логов (новые первые).
        """
        with self._lock:
            logs = list(reversed(self._logs))
        if limit is not None:
            logs = logs[:limit]
        return logs

    def clear(self) -> None:
        """Очищает историю логов."""
        with self._lock:
            self._logs.clear()

    def count(self) -> int:
        """Возвращает количество логов."""
        with self._lock:
            return len(self._logs)

    def aggregate_stats(self) -> dict[str, Any]:
        """Возвращает агрегатную статистику по всем логам."""
        from ._serialization import normalize_sql

        logs = self.all()
        total_requests = len(logs)
        total_sql = 0
        total_redis = 0
        total_elapsed_ms = 0.0
        sql_texts: dict[str, dict[str, Any]] = {}

        for log in logs:
            total_sql += log.summary.get("sql_count", 0)
            total_redis += log.summary.get("redis_count", 0)
            total_elapsed_ms += log.elapsed_ms

            for entry in log.entries:
                if entry.get("type") == EntryType.SQL.value:
                    data = entry.get("data") or {}
                    raw_sql = data.get("sql", "")
                    normalized = normalize_sql(raw_sql)
                    if normalized not in sql_texts:
                        sql_texts[normalized] = {"sql": raw_sql, "count": 0, "total_ms": 0.0}
                    sql_texts[normalized]["count"] += 1
                    sql_texts[normalized]["total_ms"] += entry.get("duration_ms") or 0

        duplicates = [
            {"sql": v["sql"], "count": v["count"], "total_ms": round(v["total_ms"], 2)}
            for v in sql_texts.values()
            if v["count"] > 1
        ]
        duplicates.sort(key=lambda x: x["count"], reverse=True)

        avg_elapsed = round(total_elapsed_ms / total_requests, 1) if total_requests else 0

        return {
            "total_requests": total_requests,
            "total_sql": total_sql,
            "total_redis": total_redis,
            "total_elapsed_ms": round(total_elapsed_ms, 1),
            "avg_elapsed_ms": avg_elapsed,
            "unique_sql": len(sql_texts),
            "duplicate_sql_count": len(duplicates),
            "duplicates": duplicates,
        }


_storage: LogStorage | None = None
_storage_lock: threading.Lock = threading.Lock()


def get_storage() -> LogStorage:
    """Возвращает глобальный экземпляр ``LogStorage`` (синглтон)."""
    global _storage
    if _storage is None:
        with _storage_lock:
            if _storage is None:
                from .settings import LOG_TOOLS
                _storage = LogStorage(max_size=LOG_TOOLS.HISTORY_SIZE)
    return _storage


def save_collector(collector: Any, status_code: int = 200) -> None:
    """Сохраняет завершённый коллектор в историю логов.

    Args:
        collector: Завершённый коллектор.
        status_code: HTTP-код ответа.
    """
    from ._serialization import serialize_entry

    parts = collector.name.split(" ", 1)
    method = parts[0] if parts else ""
    path = parts[1] if len(parts) > 1 else collector.name

    storage = get_storage()
    log = RequestLog(
        method=method,
        path=path,
        status_code=status_code,
        elapsed_ms=collector.elapsed_ms(),
        summary=collector.summary(),
        entries=[serialize_entry(entry) for entry in collector.entries],
        source=collector.source,
        command_name=collector.command_name,
    )
    storage.add(log)
