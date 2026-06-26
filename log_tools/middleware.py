from __future__ import annotations

import logging
import time
from typing import Any, Callable

from django.http import HttpRequest, HttpResponse

from .collector import Collector
from .storage import save_collector

logger = logging.getLogger("log_tools")


class LogToolsMiddleware:
    """Django middleware для автоматического логирования каждого запроса.

    Создаёт ``Collector`` для каждого входящего запроса, замеряет общее
    время выполнения и сохраняет коллектор в ``request._log_tools_collector``.
    После завершения запроса лог сохраняется в ``LogStorage`` для истории.

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

    def _save_to_file(self, collector: Any, status_code: int) -> None:
        """Сохраняет коллектор в файловое хранилище."""
        from ._serialization import serialize_entry
        from .file_storage import FileLogStorage, RequestLog, get_file_storage

        storage = get_file_storage()
        log = RequestLog(
            method=collector.name.split(" ")[0] if " " in collector.name else "",
            path=collector.name.split(" ", 1)[1] if " " in collector.name else collector.name,
            status_code=status_code,
            elapsed_ms=collector.elapsed_ms(),
            summary=collector.summary(),
            entries=[serialize_entry(entry) for entry in collector.entries],
        )
        storage.add(log)

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Обрабатывает запрос: создаёт коллектор, проксирует вызов, логирует результат.

        Запросы к самому инструменту (``/log-tools/``) не сохраняются в историю.

        Args:
            request: Входящий HTTP-запрос.

        Returns:
            HTTP-ответ.
        """
        from .settings import LOG_TOOLS
        slow_threshold: float = LOG_TOOLS.SLOW_THRESHOLD_MS

        collector = Collector(
            name=f"{request.method} {request.path}",
            slow_threshold_ms=slow_threshold,
        )
        collector.start()
        request._log_tools_collector = collector  # type: ignore[attr-defined]

        start = time.monotonic()
        response = self.get_response(request)
        duration_ms: float = (time.monotonic() - start) * 1000

        collector.add_timing(label="total", duration_ms=duration_ms)
        collector.finish()

        if not request.path.startswith("/log-tools/") and not request.path.startswith("/.well-known/"):
            if LOG_TOOLS.FILE_STORAGE:
                self._save_to_file(collector, response.status_code)
            else:
                save_collector(collector, status_code=response.status_code)

        summary = collector.summary()
        if summary["elapsed_ms"] > slow_threshold:
            logger.warning(
                "Slow request: %s %s took %.1fms | SQL: %d queries (%.1fms) | Redis: %d commands (%.1fms)",
                request.method,
                request.path,
                summary["elapsed_ms"],
                summary["sql_count"],
                summary["sql_total_ms"],
                summary["redis_count"],
                summary["redis_total_ms"],
            )

        return response


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
