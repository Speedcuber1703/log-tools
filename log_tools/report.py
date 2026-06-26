"""Генерация standalone HTML-отчёта по логам.

Переиспользует ``panel.html`` для единообразного отображения.
Создаёт самодостаточный HTML-файл, не требующий работающего сервера.
"""
from __future__ import annotations

import json
import os
import tempfile
import webbrowser
from typing import Any

from django.http import HttpRequest
from django.test import RequestFactory
from django.template.loader import render_to_string

from .file_storage import get_file_storage


def generate_report_html(title: str = "Log Tools Report") -> str:
    """Генерирует HTML-отчёт из файлового хранилища.

    Переиспользует ``panel.html`` с данными из JSONL-файла.

    Args:
        title: Заголовок отчёта.

    Returns:
        Строка с HTML-кодом отчёта.
    """
    storage = get_file_storage()
    logs = storage.all()

    # Сериализуем логи в JSON один раз на стороне Python: шаблон встраивает
    # готовую JSON-строку, а не Python-repr словарей (последнее даёт невалидный
    # JS — True/None/кортежи). Так standalone-панель открывается без сервера.
    standalone_logs = [
        {
            "method": log.method,
            "path": log.path,
            "status_code": log.status_code,
            "elapsed_ms": log.elapsed_ms,
            "timestamp": log.timestamp,
            "summary": log.summary,
            "entries": log.entries,
            "source": getattr(log, "source", "http"),
            "command_name": getattr(log, "command_name", None),
        }
        for log in logs
    ]

    context: dict[str, Any] = {
        "collector": None,
        "current_summary": {},
        "current_entries": [],
        "history": logs,
        "history_count": storage.count(),
        "aggregate": storage.aggregate_stats(),
        "source_type": "file",
        "standalone": True,
        "standalone_logs_json": json.dumps(standalone_logs, ensure_ascii=False),
        "title": title,
    }

    return render_to_string("log_tools/panel.html", context)


def open_report(title: str = "Log Tools — Статистика") -> str:
    """Генерирует HTML-отчёт и открывает его в браузере.

    Args:
        title: Заголовок отчёта.

    Returns:
        Путь к созданному HTML-файлу.
    """
    html = generate_report_html(title)

    tmp_dir = tempfile.mkdtemp(prefix="log_tools_")
    file_path = os.path.join(tmp_dir, "report.html")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html)

    webbrowser.open(f"file://{file_path}")
    return file_path
