from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .collector import Collector


@dataclass
class RequestLog:
    """Сохранённый лог одного HTTP-запроса.

    Attributes:
        method: HTTP-метод (GET, POST и т.д.).
        path: Путь запроса (/api/users/).
        status_code: HTTP-код ответа.
        elapsed_ms: Общее время обработки в миллисекундах.
        timestamp: Время завершения запроса (POCH timezone).
        summary: Сводка из ``Collector.summary()``.
        entries: Список сериализованных записей лога.
    """

    method: str
    path: str
    status_code: int
    elapsed_ms: float
    timestamp: float = field(default_factory=time.time)
    summary: dict[str, Any] = field(default_factory=dict)
    entries: list[dict[str, Any]] = field(default_factory=list)


class LogStorage:
    """Потокобезопасное хранилище последних N логов запросов.

    Использует кольцевой буфер (``deque`` с ``maxlen``).
    Потокобезопасен — все операции блокируются через ``threading.Lock``.

    Attributes:
        max_size: Максимальное количество хранимых логов.

    Example:
        >>> storage = LogStorage(max_size=100)
        >>> storage.add(request_log)
        >>> storage.all()
        [RequestLog(...), RequestLog(...)]
    """

    def __init__(self, max_size: int = 100) -> None:
        """Инициализирует хранилище.

        Args:
            max_size: Максимальное количество логов в истории.
        """
        self.max_size: int = max_size
        self._logs: deque[RequestLog] = deque(maxlen=max_size)
        self._lock: threading.Lock = threading.Lock()

    def add(self, log: RequestLog) -> None:
        """Сохраняет лог запроса в историю.

        Если история заполнена, самый старый лог удаляется автоматически.

        Args:
            log: Лог запроса для сохранения.
        """
        with self._lock:
            self._logs.append(log)

    def all(self) -> list[RequestLog]:
        """Возвращает все сохранённые логи (от нового к старому).

        Returns:
            Список логов, отсортированных по времени (новые первые).
        """
        with self._lock:
            return list(reversed(self._logs))

    def clear(self) -> None:
        """Очищает всю историю логов."""
        with self._lock:
            self._logs.clear()

    def count(self) -> int:
        """Возвращает количество сохранённых логов.

        Returns:
            Количество логов в истории.
        """
        with self._lock:
            return len(self._logs)

    def aggregate_stats(self) -> dict:
        """Возвращает агрегатную статистику по всем сохранённым логам.

        Returns:
            Словарь с общими метриками и списком дублирующихся SQL-запросов.
        """
        logs = self.all()
        return _compute_aggregate_stats(logs)


_storage: LogStorage | None = None
_storage_lock: threading.Lock = threading.Lock()


def get_storage() -> LogStorage:
    """Возвращает глобальный экземпляр ``LogStorage`` (синглтон).

    Потокобезопасная инициализация при первом вызове.

    Returns:
        Глобальное хранилище логов.
    """
    global _storage
    if _storage is None:
        with _storage_lock:
            if _storage is None:
                from .settings import LOG_TOOLS

                _storage = LogStorage(max_size=LOG_TOOLS.HISTORY_SIZE)
    return _storage


def save_collector(collector: Collector, status_code: int = 200) -> None:
    """Сохраняет завершённый коллектор в историю логов.

    Вызывается из middleware после завершения обработки запроса.

    Args:
        collector: Завершённый коллектор с записями.
        status_code: HTTP-код ответа.
    """
    from ._serialization import serialize_entry

    storage = get_storage()
    log = RequestLog(
        method=collector.name.split(" ")[0] if " " in collector.name else "",
        path=collector.name.split(" ", 1)[1] if " " in collector.name else collector.name,
        status_code=status_code,
        elapsed_ms=collector.elapsed_ms(),
        summary=collector.summary(),
        entries=[serialize_entry(entry) for entry in collector.entries],
    )
    storage.add(log)


def _compute_aggregate_stats(logs: list) -> dict:
    """Вычисляет агрегатную статистику по списку логов.

    Args:
        logs: Список ``RequestLog`` для анализа.

    Returns:
        Словарь с агрегатными метриками и дублирующимися SQL-запросами.
    """
    from ._serialization import normalize_sql

    total_requests = len(logs)
    total_sql = 0
    total_redis = 0
    total_elapsed_ms = 0.0
    sql_texts: dict[str, dict] = {}

    for log in logs:
        total_sql += log.summary.get("sql_count", 0)
        total_redis += log.summary.get("redis_count", 0)
        total_elapsed_ms += log.elapsed_ms

        for entry in log.entries:
            if entry.get("type") == "sql":
                raw_sql = entry["data"].get("sql", "")
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

    unique_sql = len(sql_texts)
    avg_elapsed = round(total_elapsed_ms / total_requests, 1) if total_requests else 0

    return {
        "total_requests": total_requests,
        "total_sql": total_sql,
        "total_redis": total_redis,
        "total_elapsed_ms": round(total_elapsed_ms, 1),
        "avg_elapsed_ms": avg_elapsed,
        "unique_sql": unique_sql,
        "duplicate_sql_count": len(duplicates),
        "duplicates": duplicates,
    }
