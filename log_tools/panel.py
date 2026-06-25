from __future__ import annotations

from django.http import HttpRequest, JsonResponse, HttpResponse
from django.urls import URLPattern, path
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from .collector import Collector, LogEntry, current_collector
from .storage import get_storage, RequestLog
from .file_storage import get_file_storage, RequestLog as FileRequestLog
from ._serialization import serialize_entry


def __get_storage():
    """Возвращает активное хранилище (файловое или in-memory)."""
    from .settings import LOG_TOOLS_FILE_STORAGE
    if LOG_TOOLS_FILE_STORAGE:
        return get_file_storage()
    return _get_storage()


def _get_request_collector(request: HttpRequest) -> Collector | None:
    """Извлекает коллектор из запроса или из thread-local.

    Сначала проверяет текущий thread-local коллектор, затем —
    коллектор, привязанный к запросу middleware.

    Args:
        request: HTTP-запрос.

    Returns:
        ``Collector`` или ``None``.
    """
    collector = current_collector()
    if collector is None:
        collector = getattr(request, "_log_tools_collector", None)
    return collector


def panel_api_view(request: HttpRequest) -> JsonResponse:
    """Возвращает данные текущего или последнего запроса в формате JSON.

    Если есть активный коллектор — возвращает его.
    Иначе — последний лог из истории.

    Args:
        request: HTTP-запрос.

    Returns:
        JSON-ответ со сводкой и списком записей.
    """
    collector = _get_request_collector(request)
    if collector is not None:
        data: dict[str, object] = {
            "summary": collector.summary(),
            "entries": [serialize_entry(entry) for entry in collector.entries],
        }
        return JsonResponse(data, json_dumps_params={"indent": 2})

    storage = _get_storage()
    logs = storage.all()
    if not logs:
        return JsonResponse({"error": "No logs available"}, status=404)

    return JsonResponse({
        "history": [_serialize_request_log(log) for log in logs[:50]],
    }, json_dumps_params={"indent": 2})


def panel_history_api_view(request: HttpRequest) -> JsonResponse:
    """Возвращает историю последних запросов в формате JSON.

    Supports query参数 ``limit`` (по умолчанию 50, максимум 200).

    Args:
        request: HTTP-запрос.

    Returns:
        JSON-ответ со списком логов.
    """
    storage = _get_storage()
    limit = min(int(request.GET.get("limit", 50)), 200)
    logs = storage.all()[:limit]
    return JsonResponse({
        "count": storage.count(),
        "logs": [_serialize_request_log(log) for log in logs],
    }, json_dumps_params={"indent": 2})


def panel_detail_api_view(request: HttpRequest, index: int) -> JsonResponse:
    """Возвращает детали конкретного лога по индексу.

    Args:
        request: HTTP-запрос.
        index: Индекс лога в истории (0 — последний).

    Returns:
        JSON-ответ с полными данными лога и обнаруженными N+1 паттернами.
    """
    from ._serialization import detect_n_plus_one

    storage = _get_storage()
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
    """Очищает историю логов.

    Args:
        request: HTTP-запрос.

    Returns:
        JSON-ответ с подтверждением.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    storage = _get_storage()
    storage.clear()
    return JsonResponse({"status": "cleared"})


def panel_html_view(request: HttpRequest) -> HttpResponse:
    """Отображает HTML-панель с историей логов (в стиле debug toolbar).

    Args:
        request: HTTP-запрос.

    Returns:
        HTML-ответ с визуализацией логов.
    """
    storage = _get_storage()
    logs = storage.all()

    collector = _get_request_collector(request)

    context: dict[str, object] = {
        "collector": collector,
        "current_summary": collector.summary() if collector else {},
        "current_entries": collector.entries if collector else [],
        "history": logs,
        "history_count": storage.count(),
        "aggregate": storage.aggregate_stats(),
    }
    return render(request, "log_tools/panel.html", context)


def _serialize_request_log(log: RequestLog) -> dict[str, object]:
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
    }


def get_urls() -> list[URLPattern]:
    """Возвращает URL-паттерны для панели логирования.

    Включает:
    - ``/log-tools/`` — HTML-панель с историей
    - ``/log-tools/api/`` — текущий/последний лог (JSON)
    - ``/log-tools/api/history/`` — история логов (JSON)
    - ``/log-tools/api/<index>/`` — детали конкретного лога (JSON)
    - ``/log-tools/api/clear/`` — очистка истории (POST)

    Returns:
        Список ``URLPattern`` для подключения в ``urlpatterns``.

    Example:
        urlpatterns = [
            *log_tools.panel.get_urls(),
            ...
        ]
    """
    return [
        path("log-tools/api/history/", panel_history_api_view, name="log_tools_history"),
        path("log-tools/api/clear/", panel_clear_api_view, name="log_tools_clear"),
        path("log-tools/api/<int:index>/", panel_detail_api_view, name="log_tools_detail"),
        path("log-tools/api/", panel_api_view, name="log_tools_api"),
        path("log-tools/", panel_html_view, name="log_tools_panel"),
    ]
