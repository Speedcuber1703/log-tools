"""Management команда для просмотра статистики логов.

Выводит общую статистику, список запросов и обнаруженные N+1 паттерны.
Поддерживает вывод в консоль, JSON и standalone HTML.

Example:
    python manage.py log_tools_stats
    python manage.py log_tools_stats --limit 10
    python manage.py log_tools_stats --json
    python manage.py log_tools_stats --clear
    python manage.py log_tools_stats --html
"""
from __future__ import annotations

import json
import os
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from log_tools.file_storage import FileLogStorage, get_file_storage
from log_tools._serialization import detect_n_plus_one
from log_tools.collector import EntryType, Source


class Command(BaseCommand):
    """Показывает статистику логов, собранных библиотекой log-tools.

    Автоматически включает файловое хранение для доступа к логам.
    """

    help = "Показывает статистику логов log-tools"

    def add_arguments(self, parser: CommandParser) -> None:
        """Определяет аргументы команды."""
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help="Количество последних запросов для отображения (по умолчанию 20)",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            dest="json_output",
            help="Вывод в формате JSON",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Очистить историю логов",
        )
        parser.add_argument(
            "--slow-threshold",
            type=float,
            default=100,
            help="Порог медленных запросов в мс (по умолчанию 100)",
        )
        parser.add_argument(
            "--html",
            action="store_true",
            help="Создать standalone HTML-отчёт и открыть в браузере",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Выполняет команду."""
        os.environ.setdefault("LOG_TOOLS_FILE_STORAGE", "True")

        storage = get_file_storage()

        if options["clear"]:
            storage.clear()
            self.stdout.write(self.style.SUCCESS("История логов очищена."))
            return

        if options["html"]:
            self._generate_html_report()
            return

        logs = storage.all()
        if not logs:
            self.stdout.write(self.style.WARNING("История логов пуста."))
            return

        if options["json_output"]:
            self._output_json(logs, options)
        else:
            self._output_text(logs, options)

    def _generate_html_report(self) -> None:
        """Генерирует standalone HTML-отчёт и открывает в браузере."""
        from log_tools.report import open_report

        storage = get_file_storage()
        logs = storage.all()
        if not logs:
            self.stdout.write(self.style.WARNING("История логов пуста."))
            return

        file_path = open_report(title="Log Tools — Статистика")
        self.stdout.write(self.style.SUCCESS(f"Отчёт создан: {file_path}"))

    def _output_text(self, logs: list, options: dict[str, Any]) -> None:
        """Выводит статистику в консоль.

        Показывает общую статистику, N+1 паттерны и детали по каждому запросу.
        """
        limit = options["limit"]
        threshold = options["slow_threshold"]
        display_logs = logs[:limit]

        total_sql = sum(log.summary.get("sql_count", 0) for log in logs)
        total_redis = sum(log.summary.get("redis_count", 0) for log in logs)
        total_elapsed = sum(log.elapsed_ms for log in logs)
        avg_elapsed = total_elapsed / len(logs) if logs else 0

        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("=== Общая статистика ==="))
        self.stdout.write(f"  Всего запросов:  {len(logs)}")
        self.stdout.write(f"  SQL запросов:    {total_sql}")
        self.stdout.write(f"  Redis команд:    {total_redis}")
        self.stdout.write(f"  Среднее время:   {avg_elapsed:.1f}мс")
        self.stdout.write("")

        n_plus_one_all: list[dict[str, Any]] = []
        for log in logs:
            n_plus_one_all.extend(detect_n_plus_one(log.entries))

        if n_plus_one_all:
            self.stdout.write(self.style.WARNING("=== Обнаруженные N+1 паттерны ==="))
            seen: set[tuple[str, int]] = set()
            for np1 in n_plus_one_all:
                key = (np1["table"], np1["count"])
                if key not in seen:
                    seen.add(key)
                    self.stdout.write(
                        f"  {self.style.WARNING(np1['table'])}: "
                        f"{np1['count']} запросов ({np1['total_ms']}мс)"
                    )
            self.stdout.write("")

        self.stdout.write(self.style.HTTP_INFO(f"=== Последние {len(display_logs)} запросов ==="))
        self.stdout.write("")

        for i, log in enumerate(display_logs):
            status_color = self.style.SUCCESS if log.status_code < 400 else self.style.ERROR
            slow_marker = self.style.WARNING(" SLOW") if log.elapsed_ms > threshold else ""
            source_info = f" [{log.source.value}]" if log.source != Source.HTTP else ""
            command_info = f" ({log.command_name})" if log.command_name else ""

            self.stdout.write(
                f"  {i+1:3d}. {log.method:6s} {log.path}"
                f"  {status_color(str(log.status_code))}"
                f"  {log.elapsed_ms:.1f}мс{slow_marker}{source_info}{command_info}"
            )
            self.stdout.write(
                f"       SQL: {log.summary.get('sql_count', 0)}  "
                f"Redis: {log.summary.get('redis_count', 0)}  "
                f"Entries: {log.summary.get('total_entries', 0)}"
            )

            for entry in log.entries:
                entry_type = entry.get("type")
                if entry_type == EntryType.SQL.value:
                    sql = entry.get("data", {}).get("sql", "")
                    dur = entry.get("duration_ms", 0)
                    normalized = entry.get("data", {}).get("normalized_sql", "")
                    dup_count = log.summary.get("sql_duplicates", {}).get(normalized, 1)
                    dup_marker = f" {self.style.WARNING(f'x{dup_count}')}" if dup_count > 1 else ""
                    self.stdout.write(
                        f"         {self.style.SQL_KEYWORD('SQL')}"
                        f" {dur:.2f}мс{dup_marker}: {sql[:80]}"
                    )
                elif entry_type == EntryType.REDIS.value:
                    cmd = entry.get("data", {}).get("command", "")
                    args = entry.get("data", {}).get("args", ())
                    dur = entry.get("duration_ms", 0)
                    self.stdout.write(
                        f"         {self.style.HTTP_INFO('REDIS')}"
                        f" {dur:.2f}мс: {cmd} {args}"
                    )

            self.stdout.write("")

    def _output_json(self, logs: list, options: dict[str, Any]) -> None:
        """Выводит статистику в формате JSON.

        Включает все логи с записями и обнаруженными N+1 паттернами.
        """
        limit = options["limit"]
        display_logs = logs[:limit]

        data: dict[str, Any] = {"total_logs": len(logs), "logs": []}

        for log in display_logs:
            data["logs"].append({
                "method": log.method,
                "path": log.path,
                "status_code": log.status_code,
                "elapsed_ms": log.elapsed_ms,
                "summary": log.summary,
                "n_plus_one": detect_n_plus_one(log.entries),
                "entries": log.entries,
                "source": log.source.value,
                "command_name": log.command_name,
            })

        self.stdout.write(json.dumps(data, indent=2, ensure_ascii=False))
