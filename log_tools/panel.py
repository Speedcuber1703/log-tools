"""Панель логирования для Django.

Предоставляет HTML-интерфейс и JSON API для просмотра логов.
"""
from __future__ import annotations

from typing import Any, Union

from django.http import HttpRequest, JsonResponse, HttpResponse
from django.urls import URLPattern, path
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from .collector import Collector, Source, current_collector
from .storage import LogStorage, get_storage, RequestLog
from .file_storage import FileLogStorage, get_file_storage
from ._serialization import serialize_entry

StorageType = Union[LogStorage, FileLogStorage]


def _get_storage_for_request(request: HttpRequest) -> StorageType:
    """Возвращает хранилище в зависимости от параметра ``source``.

    Args:
        request: HTTP-запрос.

    Returns:
        Экземпляр хранилища.
    """
    if request.GET.get("source") == "file":
        return get_file_storage()
    from .settings import LOG_TOOLS
    if LOG_TOOLS.FILE_STORAGE:
        return get_file_storage()
    return get_storage()


def _get_request_collector(request: HttpRequest) -> Collector | None:
    """Извлекает коллектор из запроса или из thread-local."""
    collector = current_collector()
    if collector is None:
        collector = getattr(request, "_log_tools_collector", None)
    return collector


def _safe_int(value: str | None, default: int, min_val: int = 0, max_val: int | None = None) -> int:
    """Безопасно преобразует строку в int с дефолтом и ограничениями."""
    if value is None:
        return default
    try:
        result = int(value)
    except (ValueError, TypeError):
        return default
    result = max(min_val, result)
    if max_val is not None:
        result = min(max_val, result)
    return result


def panel_api_view(request: HttpRequest) -> JsonResponse:
    """Возвращает данные текущего или последнего запроса в формате JSON."""
    collector = _get_request_collector(request)
    if collector is not None:
        data: dict[str, Any] = {
            "summary": collector.summary(),
            "entries": [serialize_entry(entry) for entry in collector.entries],
        }
        return JsonResponse(data, json_dumps_params={"indent": 2})

    storage = _get_storage_for_request(request)
    logs = storage.all()
    if not logs:
        return JsonResponse({"error": "No logs available"}, status=404)

    return JsonResponse({
        "history": [_serialize_request_log(log) for log in logs[:50]],
    }, json_dumps_params={"indent": 2})


def panel_history_api_view(request: HttpRequest) -> JsonResponse:
    """Возвращает историю последних запросов в формате JSON."""
    storage = _get_storage_for_request(request)
    limit = _safe_int(request.GET.get("limit"), default=50, min_val=1, max_val=200)
    logs = storage.all(limit=limit)
    return JsonResponse({
        "count": storage.count(),
        "logs": [_serialize_request_log(log) for log in logs],
    }, json_dumps_params={"indent": 2})


def panel_detail_api_view(request: HttpRequest, index: int) -> JsonResponse:
    """Возвращает детали конкретного лога по индексу."""
    from ._serialization import detect_n_plus_one

    storage = _get_storage_for_request(request)
    logs = storage.all()
    if index < 0 or index >= len(logs):
        return JsonResponse({"error": "Log not found"}, status=404)

    log = logs[index]
    n_plus_one = detect_n_plus_one(log.entries)

    return JsonResponse({
        "log": _serialize_request_log(log),
        "entries": log.entries,
        "n_plus_one": n_plus_one,
    }, json_dumps_params={"indent": 2})


@csrf_exempt
def panel_clear_api_view(request: HttpRequest) -> JsonResponse:
    """Очищает историю логов."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    storage = _get_storage_for_request(request)
    storage.clear()
    return JsonResponse({"status": "cleared"})


def panel_html_view(request: HttpRequest) -> HttpResponse:
    """Отображает HTML-панель с историей логов."""
    storage = _get_storage_for_request(request)
    logs = storage.all()
    collector = _get_request_collector(request)

    context: dict[str, Any] = {
        "collector": collector,
        "current_summary": collector.summary() if collector else {},
        "current_entries": collector.entries if collector else [],
        "history": logs,
        "history_count": storage.count(),
        "aggregate": storage.aggregate_stats() if logs else {},
        "source_type": request.GET.get("source", Source.HTTP.value),
        "standalone": False,
    }
    return render(request, "log_tools/panel.html", context)


def _serialize_request_log(log: RequestLog) -> dict[str, Any]:
    """Сериализует ``RequestLog`` в словарь для JSON.

    Args:
        log: Лог запроса.

    Returns:
        Словарь с данными лога.
    """
    return {
        "method": log.method,
        "path": log.path,
        "status_code": log.status_code,
        "elapsed_ms": log.elapsed_ms,
        "timestamp": log.timestamp,
        "summary": log.summary,
        "entries_count": len(log.entries),
        "source": log.source.value,
        "command_name": log.command_name,
    }


def get_urls() -> list[URLPattern]:
    """Возвращает URL-паттерны для панели логирования."""
    return [
        path("log-tools/api/history/", panel_history_api_view, name="log_tools_history"),
        path("log-tools/api/clear/", panel_clear_api_view, name="log_tools_clear"),
        path("log-tools/api/<int:index>/", panel_detail_api_view, name="log_tools_detail"),
        path("log-tools/api/", panel_api_view, name="log_tools_api"),
        path("log-tools/", panel_html_view, name="log_tools_panel"),
    ]
