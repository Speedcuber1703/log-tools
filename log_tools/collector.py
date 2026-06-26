"""Сборщик лог-записей для одного запроса или блока кода.

Предоставляет ``Collector`` для накопления SQL, Redis и timing-записей.
Поддерживает вложенность через thread-local хранилище.
"""
from __future__ import annotations

import time
import threading
import types
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EntryType(str, Enum):
    """Тип записи в логе."""

    TIMING = "timing"
    SQL = "sql"
    REDIS = "redis"
    LOG = "log"


class Source(str, Enum):
    """Источник логов."""

    HTTP = "http"
    COMMAND = "command"


class LogLevel(str, Enum):
    """Уровень логирования."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class LogEntry:
    """Одна запись лога.

    Attributes:
        type: Тип записи (SQL, REDIS, TIMING, LOG).
        timestamp: Время создания записи (монотонные секунды).
        data: Дополнительные данные записи. Структура зависит от ``type``:
            - SQL: ``{"sql": str, "params": Any, "alias": str}``
            - REDIS: ``{"command": str, "args": tuple, "kwargs": dict, "client_name": str}``
            - TIMING: ``{"label": str}``
            - LOG: ``{"message": str, "level": str}``
        duration_ms: Время выполнения в миллисекундах (``None`` для LOG).
        is_slow: ``True`` если ``duration_ms`` превысила порог медленных операций.
    """

    type: EntryType
    timestamp: float = field(default_factory=time.monotonic)
    data: dict[str, Any] = field(default_factory=dict)
    duration_ms: float | None = None
    is_slow: bool = False


_collector_var = threading.local()


class Collector:
    """Сборщик лог-записей для одного запроса или блока кода.

    Использует thread-local хранилище для изоляции вложений.
    Вложенные коллекторы корректно восстанавливают предыдущий при ``finish()``.

    Example:
        >>> collector = Collector(name="my-request")
        >>> collector.start()
        >>> collector.add_sql("SELECT 1", duration_ms=2.5)
        >>> collector.finish()
        >>> collector.summary()
        {"name": "my-request", "elapsed_ms": 12.3, "sql_count": 1, ...}
    """

    def __init__(
        self,
        name: str | None = None,
        slow_threshold_ms: float = 100,
        source: Source = Source.HTTP,
        command_name: str | None = None,
    ) -> None:
        """Инициализирует коллектор.

        Args:
            name: Имя коллектора для идентификации в логах.
            slow_threshold_ms: Порог медленных операций в миллисекундах.
            source: Источник логов (HTTP или COMMAND).
            command_name: Имя management-команды.
        """
        self.name: str = name or "default"
        self.slow_threshold_ms: float = slow_threshold_ms
        self.source: Source = source
        self.command_name: str | None = command_name
        self.entries: list[LogEntry] = []
        self._start_time: float = 0.0
        self._prev: Collector | None = None

    def __enter__(self) -> Collector:
        """Активирует коллектор при входе в контекст."""
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Деактивирует коллектор при выходе из контекста."""
        self.finish()

    def start(self) -> None:
        """Активирует коллектор: фиксирует время начала и становится текущим.

        Если уже есть активный коллектор, сохраняет его как предыдущий
        для корректного восстановления при завершении.
        """
        self._start_time = time.monotonic()
        self._prev = getattr(_collector_var, "collector", None)
        _collector_var.collector = self

    def finish(self) -> None:
        """Деактивирует коллектор и восстанавливает предыдущий."""
        if getattr(_collector_var, "collector", None) is self:
            _collector_var.collector = self._prev
        self._prev = None

    def elapsed_ms(self) -> float:
        """Возвращает время работы коллектора в миллисекундах.

        Returns:
            Время в миллисекундах с момента ``start()``.
        """
        return (time.monotonic() - self._start_time) * 1000

    def add(self, entry: LogEntry) -> None:
        """Добавляет запись в лог.

        Если ``duration_ms`` превышает ``slow_threshold_ms``,
        запись помечается как медленная.

        Args:
            entry: Запись лога для добавления.
        """
        if entry.duration_ms and entry.duration_ms > self.slow_threshold_ms:
            entry.is_slow = True
        self.entries.append(entry)

    def add_sql(
        self,
        sql: str,
        params: Any = None,
        duration_ms: float = 0.0,
        alias: str = "default",
    ) -> None:
        """Добавляет запись о SQL-запросе.

        Args:
            sql: Текст SQL-запроса.
            params: Параметры запроса.
            duration_ms: Время выполнения в миллисекундах.
            alias: Имя базы данных (из ``DATABASES``).
        """
        self.add(LogEntry(
            type=EntryType.SQL,
            data={"sql": sql, "params": params, "alias": alias},
            duration_ms=duration_ms,
        ))

    def add_redis(
        self,
        command: str,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        duration_ms: float = 0.0,
        client_name: str = "",
    ) -> None:
        """Добавляет запись о команде Redis.

        Args:
            command: Имя команды (например, ``"GET"``).
            args: Позиционные аргументы команды.
            kwargs: Именованные аргументы команды.
            duration_ms: Время выполнения в миллисекундах.
            client_name: Имя Redis-клиента.
        """
        self.add(LogEntry(
            type=EntryType.REDIS,
            data={
                "command": command,
                "args": args,
                "kwargs": kwargs or {},
                "client_name": client_name,
            },
            duration_ms=duration_ms,
        ))

    def add_timing(self, label: str, duration_ms: float) -> None:
        """Добавляет замер времени выполнения блока кода.

        Args:
            label: Название блока.
            duration_ms: Время выполнения в миллисекундах.
        """
        self.add(LogEntry(
            type=EntryType.TIMING,
            data={"label": label},
            duration_ms=duration_ms,
        ))

    def add_log(
        self,
        message: str,
        level: LogLevel = LogLevel.INFO,
        **extra: Any,
    ) -> None:
        """Добавляет произвольное текстовое сообщение в лог.

        Args:
            message: Текст сообщения.
            level: Уровень логирования.
            **extra: Дополнительные данные в ``data`` записи.
        """
        self.add(LogEntry(
            type=EntryType.LOG,
            data={"message": message, "level": level.value, **extra},
        ))

    def sql_entries(self) -> list[LogEntry]:
        """Возвращает SQL-записи.

        Returns:
            Список записей типа ``EntryType.SQL``.
        """
        return [e for e in self.entries if e.type == EntryType.SQL]

    def redis_entries(self) -> list[LogEntry]:
        """Возвращает Redis-записи.

        Returns:
            Список записей типа ``EntryType.REDIS``.
        """
        return [e for e in self.entries if e.type == EntryType.REDIS]

    def timing_entries(self) -> list[LogEntry]:
        """Возвращает записи с замерами времени.

        Returns:
            Список записей типа ``EntryType.TIMING``.
        """
        return [e for e in self.entries if e.type == EntryType.TIMING]

    def summary(self) -> dict[str, Any]:
        """Формирует сводку по всем записям коллектора.

        Returns:
            Словарь с ключами: ``name``, ``elapsed_ms``, ``sql_count``,
            ``sql_total_ms``, ``sql_slow``, ``redis_count``, ``redis_total_ms``,
            ``redis_slow``, ``total_entries``, ``sql_duplicates``.
        """
        from ._serialization import normalize_sql

        sql = self.sql_entries()
        redis = self.redis_entries()
        total_sql_ms = sum(e.duration_ms or 0 for e in sql)
        total_redis_ms = sum(e.duration_ms or 0 for e in redis)

        sql_dup_map: dict[str, int] = {}
        for entry in sql:
            raw = entry.data.get("sql", "")
            normalized = normalize_sql(raw)
            sql_dup_map[normalized] = sql_dup_map.get(normalized, 0) + 1

        return {
            "name": self.name,
            "elapsed_ms": self.elapsed_ms(),
            "sql_count": len(sql),
            "sql_total_ms": total_sql_ms,
            "sql_slow": [
                {"sql": e.data.get("sql", ""), "duration_ms": e.duration_ms, "params": e.data.get("params")}
                for e in sql if e.is_slow
            ],
            "redis_count": len(redis),
            "redis_total_ms": total_redis_ms,
            "redis_slow": [
                {"command": e.data.get("command", ""), "duration_ms": e.duration_ms}
                for e in redis if e.is_slow
            ],
            "total_entries": len(self.entries),
            "sql_duplicates": sql_dup_map,
        }


def current_collector() -> Collector | None:
    """Возвращает текущий активный коллектор для данного потока.

    Returns:
        Текущий ``Collector`` или ``None``.
    """
    return getattr(_collector_var, "collector", None)
