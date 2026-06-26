"""Django middleware для автоматического логирования запросов.

Создаёт ``Collector`` для каждого входящего запроса, замеряет общее
время выполнения и сохраняет результат в хранилище.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from django.http import HttpRequest, HttpResponse

from .collector import Collector, Source
from .storage import save_collector

logger = logging.getLogger("log_tools")

_SKIP_PATHS = ("/log-tools/", "/.well-known/")


class LogToolsMiddleware:
    """Django middleware для автоматического логирования запросов.

    Создаёт ``Collector`` для каждого входящего запроса, замеряет общее
    время выполнения и сохраняет коллектор в ``request._log_tools_collector``.
    Если запрос выполняется дольше порога ``LOG_TOOLS_SLOW_THRESHOLD_MS``,
    в лог пишется предупреждение.

    Example:
        Добавьте в ``MIDDLEWARE``::

            MIDDLEWARE = [
                ...
                "log_tools.middleware.LogToolsMiddleware",
            ]
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        """Инициализирует middleware.

        Args:
            get_response: Callable, возвращающий ``HttpResponse`` для запроса.
        """
        self.get_response: Callable[[HttpRequest], HttpResponse] = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Обрабатывает запрос: создаёт коллектор, проксирует вызов, логирует.

        Запросы к ``/log-tools/`` и ``/.well-known/`` не сохраняются.

        Args:
            request: Входящий HTTP-запрос.

        Returns:
            HTTP-ответ.
        """
        from .settings import LOG_TOOLS

        collector = Collector(
            name=f"{request.method} {request.path}",
            slow_threshold_ms=LOG_TOOLS.SLOW_THRESHOLD_MS,
            source=Source.HTTP,
        )
        collector.start()
        request._log_tools_collector = collector  # type: ignore[attr-defined]

        start = time.monotonic()
        response = self.get_response(request)
        duration_ms: float = (time.monotonic() - start) * 1000

        collector.add_timing(label="total", duration_ms=duration_ms)
        collector.finish()

        if not any(request.path.startswith(p) for p in _SKIP_PATHS):
            if LOG_TOOLS.FILE_STORAGE:
                self._save_to_file(collector, response.status_code)
            else:
                save_collector(collector, status_code=response.status_code)

        summary = collector.summary()
        slow_threshold: float = getattr(
            request, "_log_tools_slow_threshold", LOG_TOOLS.SLOW_THRESHOLD_MS,
        )
        if summary["elapsed_ms"] > slow_threshold:
            logger.warning(
                "Slow request: %s %s took %.1fms | SQL: %d (%.1fms) | Redis: %d (%.1fms)",
                request.method,
                request.path,
                summary["elapsed_ms"],
                summary["sql_count"],
                summary["sql_total_ms"],
                summary["redis_count"],
                summary["redis_total_ms"],
            )

        return response

    def _save_to_file(self, collector: Collector, status_code: int) -> None:
        """Сохраняет коллектор в файловое хранилище.

        Args:
            collector: Коллектор с записями.
            status_code: HTTP-код ответа.
        """
        from ._serialization import serialize_entry
        from .file_storage import get_file_storage, RequestLog

        parts = collector.name.split(" ", 1)
        method = parts[0] if parts else ""
        path = parts[1] if len(parts) > 1 else collector.name

        storage = get_file_storage()
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


def get_collector_from_request(request: HttpRequest) -> Collector | None:
    """Извлекает коллектор из HTTP-запроса.

    Коллектор привязывается к запросу в ``LogToolsMiddleware.__call__()``
    и доступен через ``request._log_tools_collector``.

    Args:
        request: HTTP-запрос.

    Returns:
        ``Collector`` привязанный к запросу, или ``None`` если middleware
        не активен.
    """
    return getattr(request, "_log_tools_collector", None)
