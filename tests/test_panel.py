"""Тесты HTML-панели, standalone-отчёта и режима ?source=file."""
import json
import re
import tempfile

import pytest
from django.test import RequestFactory, override_settings

import log_tools.file_storage as file_storage
from log_tools.file_storage import RequestLog as FileRequestLog
from log_tools.collector import Collector
from log_tools._serialization import serialize_entry
from log_tools import panel, report
from log_tools.storage import save_collector, get_storage


def _sample_collector():
    """Коллектор с медленными и быстрыми записями всех типов."""
    c = Collector("GET /api/users", slow_threshold_ms=10)
    c.start()
    c.add_sql("SELECT * FROM auth_user WHERE id = 5", duration_ms=2.0)        # быстрый
    c.add_sql("SELECT * FROM auth_user WHERE id = 9999", duration_ms=120.0)   # медленный
    c.add_redis("GET", ("sess:1",), duration_ms=0.4)                          # быстрый
    c.add_timing("total", 130.0)
    c.finish()
    return c


@pytest.fixture(autouse=True)
def _reset_storages():
    """Сбрасываем синглтоны хранилищ между тестами."""
    get_storage().clear()
    file_storage._file_storage = None
    yield
    get_storage().clear()
    file_storage._file_storage = None


class TestPanelRendering:
    def test_panel_html_opens(self):
        save_collector(_sample_collector(), status_code=200)
        resp = panel.panel_html_view(RequestFactory().get("/log-tools/"))
        html = resp.content.decode()
        assert resp.status_code == 200
        assert "history-table" in html
        # Осколок `});` ломал весь <script> и панель не открывалась.
        assert "});\n}" not in html

    def test_detail_shows_all_entries_not_only_slow(self):
        save_collector(_sample_collector(), status_code=200)
        resp = panel.panel_detail_api_view(RequestFactory().get("/log-tools/api/0/"), index=0)
        data = json.loads(resp.content)
        # В деталке должны быть все записи: оба SQL (быстрый и медленный),
        # Redis и timing — не только медленные.
        types = sorted(e["type"] for e in data["entries"])
        assert types == ["redis", "sql", "sql", "timing"]
        slow_flags = [e["is_slow"] for e in data["entries"] if e["type"] == "sql"]
        assert slow_flags == [False, True]


@pytest.fixture
def file_storage_with_log():
    """Файловое хранилище с одним сохранённым логом."""
    file_storage._file_storage = None
    path = tempfile.mktemp(suffix=".jsonl")
    with override_settings(LOG_TOOLS_FILE_STORAGE=True, LOG_TOOLS_FILE_PATH=path):
        c = _sample_collector()
        storage = file_storage.get_file_storage()
        storage.add(FileRequestLog(
            method="GET", path="/api/users", status_code=200, elapsed_ms=130.0,
            summary=c.summary(), entries=[serialize_entry(e) for e in c.entries],
        ))
        yield storage
    file_storage._file_storage = None


class TestStandaloneReport:
    def test_standalone_logs_is_valid_json(self, file_storage_with_log):
        html = report.generate_report_html("Отчёт")
        match = re.search(r"const STANDALONE_LOGS = (.*?);\n", html, re.S)
        assert match is not None
        # Раньше сюда подставлялся Python-repr (True/None/кортежи) → невалидный JS.
        parsed = json.loads(match.group(1))
        assert len(parsed) == 1
        assert len(parsed[0]["entries"]) == 4


class TestSourceFile:
    def test_panel_uses_file_storage_with_source_file(self, file_storage_with_log):
        request = RequestFactory().get("/log-tools/?source=file")
        resp = panel.panel_html_view(request)
        html = resp.content.decode()
        assert resp.status_code == 200
        assert "/api/users" in html

    def test_detail_api_reads_file_storage_with_source_file(self, file_storage_with_log):
        request = RequestFactory().get("/log-tools/api/0/?source=file")
        resp = panel.panel_detail_api_view(request, index=0)
        data = json.loads(resp.content)
        assert len(data["entries"]) == 4
