import pytest
from django.core.management import call_command
from django.test import override_settings

import log_tools.file_storage as file_storage
import log_tools.report as report
from log_tools.file_storage import RequestLog


@pytest.fixture
def seeded_file_storage(tmp_path):
    file_storage._file_storage = None
    path = str(tmp_path / "logs.jsonl")
    with override_settings(LOG_TOOLS_FILE_STORAGE=True, LOG_TOOLS_FILE_PATH=path):
        storage = file_storage.get_file_storage()
        storage.add(RequestLog(method="GET", path="/x", status_code=200, elapsed_ms=1.0))
        yield storage
    file_storage._file_storage = None


def test_html_command_calls_open_report_with_title_only(seeded_file_storage, monkeypatch):
    calls = {}

    # Реальная сигнатура open_report принимает только `title`; если команда
    # передаёт позиционный `logs`, эта заглушка падает с TypeError — как и баг.
    def fake_open_report(title="Log Tools"):
        calls["title"] = title
        return "/tmp/report.html"

    monkeypatch.setattr(report, "open_report", fake_open_report)

    call_command("log_tools_stats", "--html")

    assert "title" in calls
