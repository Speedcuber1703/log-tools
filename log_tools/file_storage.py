"""Файловое хранилище логов для персистентного хранения.

Сохраняет логи в JSONL-файл между перезапусками приложения.
Подключается через настройку ``LOG_TOOLS_FILE_STORAGE = True``.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from .collector import EntryType, Source

logger = logging.getLogger(__name__)


@dataclass
class RequestLog:
    """Сохранённый лог одного HTTP-запроса или команды.

    Attributes:
        method: HTTP-метод или имя команды.
        path: Путь запроса или описание блока кода.
        status_code: HTTP-статус (200 для команд).
        elapsed_ms: Время выполнения в миллисекундах.
        timestamp: Unix-таймстемп создания.
        summary: Сводка из ``Collector.summary()``.
        entries: Список сериализованных записей лога.
        source: Источник логов (HTTP или COMMAND).
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


class FileLogStorage:
    """Файловое хранилище логов в формате JSONL.

    Потокобезопасно для записи через ``threading.Lock``.

    Attributes:
        file_path: Путь к файлу логов.
        max_size: Максимальное количество хранимых логов.
    """

    def __init__(self, file_path: str, max_size: int = 500) -> None:
        self.file_path: str = file_path
        self.max_size: int = max_size
        self._lock: threading.Lock = threading.Lock()

    def add(self, log: RequestLog) -> None:
        """Сохраняет лог запроса в файл.

        Args:
            log: Лог запроса для сохранения.
        """
        with self._lock:
            with open(self.file_path, "a", encoding="utf-8") as f:
                source_val = log.source.value if hasattr(log.source, "value") else log.source
                record = {
                    "method": log.method,
                    "path": log.path,
                    "status_code": log.status_code,
                    "elapsed_ms": log.elapsed_ms,
                    "timestamp": log.timestamp,
                    "summary": log.summary,
                    "entries": log.entries,
                    "source": source_val,
                    "command_name": log.command_name,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

            self._truncate_if_needed()

    def _truncate_if_needed(self) -> None:
        """Обрезает файл, оставляя последние ``max_size`` записей."""
        logs = self._read_all()
        if len(logs) > self.max_size:
            logs = logs[-self.max_size:]
            with open(self.file_path, "w", encoding="utf-8") as f:
                for record in logs:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _read_all(self) -> list[dict[str, Any]]:
        """Читает все записи из файла.

        Returns:
            Список словарей с данными логов.
        """
        if not os.path.exists(self.file_path):
            return []

        records: list[dict[str, Any]] = []
        with open(self.file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.debug("Пропуск повреждённой строки в %s", self.file_path)
                        continue
        return records

    def all(self, limit: int | None = None) -> list[RequestLog]:
        """Возвращает сохранённые логи.

        Args:
            limit: Максимальное количество логов. ``None`` — все.

        Returns:
            Список логов, отсортированных по времени (новые первые).
        """
        records = self._read_all()
        records.reverse()

        if limit is not None:
            records = records[:limit]

        return [
            RequestLog(
                method=r["method"],
                path=r["path"],
                status_code=r["status_code"],
                elapsed_ms=r["elapsed_ms"],
                timestamp=r.get("timestamp", 0),
                summary=r.get("summary", {}),
                entries=r.get("entries", []),
                source=Source(r.get("source", Source.HTTP.value)),
                command_name=r.get("command_name"),
            )
            for r in records
        ]

    def clear(self) -> None:
        """Очищает файл логов."""
        with self._lock:
            if os.path.exists(self.file_path):
                os.remove(self.file_path)

    def count(self) -> int:
        """Возвращает количество сохранённых логов."""
        if not os.path.exists(self.file_path):
            return 0
        with open(self.file_path, "r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())

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


_file_storage: FileLogStorage | None = None
_file_storage_lock: threading.Lock = threading.Lock()


def get_file_storage() -> FileLogStorage:
    """Возвращает глобальный экземпляр ``FileLogStorage`` (синглтон)."""
    global _file_storage
    if _file_storage is None:
        with _file_storage_lock:
            if _file_storage is None:
                from django.conf import settings
                from .settings import LOG_TOOLS

                base_dir = getattr(settings, "BASE_DIR", ".")
                file_path = getattr(settings, "LOG_TOOLS_FILE_PATH", None)
                if file_path is None:
                    file_path = os.path.join(str(base_dir), "log_tools_logs.jsonl")

                _file_storage = FileLogStorage(file_path=file_path, max_size=LOG_TOOLS.HISTORY_SIZE)
    return _file_storage
