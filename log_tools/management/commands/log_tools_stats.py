from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from log_tools.file_storage import get_file_storage
from log_tools._serialization import detect_n_plus_one


class Command(BaseCommand):
    """Показывает статистику логов, собранных библиотекой log-tools.

    Выводит общую статистику, список запросов и обнаруженные N+1 паттерны.

    Example:
        python manage.py log_tools_stats
        python manage.py log_tools_stats --limit 10
        python manage.py log_tools_stats --json
        python manage.py log_tools_stats --clear
    """

    help = "Показывает статистику логов log-tools"

    def add_arguments(self, parser: CommandParser) -> None:
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

    def handle(self, *args: Any, **options: Any) -> None:
        storage = get_file_storage()

        if options["clear"]:
            storage.clear()
            self.stdout.write(self.style.SUCCESS("История логов очищена."))
            return

        logs = storage.all()
        if not logs:
            self.stdout.write(self.style.WARNING("История логов пуста."))
            return

        if options["json_output"]:
            self._output_json(logs, options)
        else:
            self._output_text(logs, options)

    def _output_text(self, logs: list, options: dict) -> None:
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

        n_plus_one_all = []
        for log in logs:
            np1 = detect_n_plus_one(log.entries)
            n_plus_one_all.extend(np1)

        if n_plus_one_all:
            self.stdout.write(self.style.WARNING("=== Обнаруженные N+1 паттерны ==="))
            seen = set()
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

            self.stdout.write(
                f"  {i+1:3d}. {log.method:6s} {log.path}"
                f"  {status_color(str(log.status_code))}"
                f"  {log.elapsed_ms:.1f}мс{slow_marker}"
            )
            self.stdout.write(
                f"       SQL: {log.summary.get('sql_count', 0)}  "
                f"Redis: {log.summary.get('redis_count', 0)}  "
                f"Entries: {log.summary.get('total_entries', 0)}"
            )

            for entry in log.entries:
                if entry.get("type") == "sql":
                    sql = entry.get("data", {}).get("sql", "")
                    dur = entry.get("duration_ms", 0)
                    normalized = entry.get("data", {}).get("normalized_sql", "")
                    dup_count = log.summary.get("sql_duplicates", {}).get(normalized, 1)
                    dup_marker = f" {self.style.WARNING(f'x{dup_count}')}" if dup_count > 1 else ""
                    self.stdout.write(
                        f"         {self.style.SQL_KEYWORD('SQL')}"
                        f" {dur:.2f}мс{dup_marker}: {sql[:80]}"
                    )
                elif entry.get("type") == "redis":
                    cmd = entry.get("data", {}).get("command", "")
                    args = entry.get("data", {}).get("args", ())
                    dur = entry.get("duration_ms", 0)
                    self.stdout.write(
                        f"         {self.style.HTTP_INFO('REDIS')}"
                        f" {dur:.2f}мс: {cmd} {args}"
                    )

            self.stdout.write("")

    def _output_json(self, logs: list, options: dict) -> None:
        limit = options["limit"]
        display_logs = logs[:limit]

        data = {
            "total_logs": len(logs),
            "logs": []
        }

        for log in display_logs:
            np1 = detect_n_plus_one(log.entries)
            data["logs"].append({
                "method": log.method,
                "path": log.path,
                "status_code": log.status_code,
                "elapsed_ms": log.elapsed_ms,
                "summary": log.summary,
                "n_plus_one": np1,
                "entries": log.entries,
            })

        self.stdout.write(json.dumps(data, indent=2, ensure_ascii=False))
