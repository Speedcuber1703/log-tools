"""Генерация standalone HTML-отчёта по логам.

Переиспользует ``panel.html`` для единообразного отображения.
Создаёт самодостаточный HTML-файл со встроенными данными,
не требующий работающего Django-сервера.
"""
from __future__ import annotations

import json
import os
import tempfile
import webbrowser
from typing import Any

from django.template.loader import render_to_string

from .file_storage import get_file_storage


def generate_report_html(title: str = "Log Tools Report") -> str:
    """Генерирует HTML-отчёт из файлового хранилища.

    Читает все логи из JSONL-файла и рендерит ``panel.html``
    в standalone-режиме (данные встроены в HTML).

    Args:
        title: Заголовок отчёта.

    Returns:
        Строка с HTML-кодом отчёта.
    """
    storage = get_file_storage()
    logs = storage.all()

    logs_data = [
        {
            "method": log.method,
            "path": log.path,
            "status_code": log.status_code,
            "elapsed_ms": log.elapsed_ms,
            "timestamp": log.timestamp,
            "summary": log.summary,
            "entries": log.entries,
            "source": log.source.value if hasattr(log.source, "value") else log.source,
            "command_name": log.command_name,
        }
        for log in logs
    ]

    context: dict[str, Any] = {
        "collector": None,
        "current_summary": {},
        "current_entries": [],
        "history": logs,
        "history_count": storage.count(),
        "aggregate": storage.aggregate_stats() if logs else {},
        "source_type": "file",
        "standalone": True,
        "standalone_logs_json": json.dumps(logs_data, ensure_ascii=False),
        "title": title,
    }

    return render_to_string("log_tools/panel.html", context)


def open_report(title: str = "Log Tools Report") -> str:
    """Генерирует HTML-отчёт и открывает его в браузере.

    Создаёт временный HTML-файл и открывает через ``webbrowser.open()``.

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
