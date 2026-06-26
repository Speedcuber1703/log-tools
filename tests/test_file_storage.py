import pytest
from django.test import override_settings

import log_tools.file_storage as file_storage
from log_tools.file_storage import FileLogStorage, RequestLog
from log_tools import LogContext


class TestFileStorageRoundtrip:
    def test_source_and_command_name_persist(self, tmp_path):
        path = str(tmp_path / "logs.jsonl")
        storage = FileLogStorage(file_path=path, max_size=100)
        storage.add(RequestLog(
            method="management",
            path="my_command",
            status_code=200,
            elapsed_ms=1.0,
            source="command",
            command_name="my_command",
        ))
        logs = storage.all()
        assert len(logs) == 1
        assert logs[0].source == "command"
        assert logs[0].command_name == "my_command"

    def test_defaults_for_legacy_records(self, tmp_path):
        path = str(tmp_path / "logs.jsonl")
        # Запись, сделанная старой версией без новых ключей.
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"method": "GET", "path": "/x", "status_code": 200, '
                    '"elapsed_ms": 1.0, "timestamp": 0, "summary": {}, "entries": []}\n')
        log = FileLogStorage(file_path=path).all()[0]
        assert log.source == "http"
        assert log.command_name is None


@pytest.fixture
def file_storage_singleton(tmp_path):
    """Направляет синглтон файлового хранилища на временный файл и сбрасывает его."""
    file_storage._file_storage = None
    path = str(tmp_path / "logs.jsonl")
    with override_settings(LOG_TOOLS_FILE_STORAGE=True, LOG_TOOLS_FILE_PATH=path):
        yield path
    file_storage._file_storage = None


class TestLogContextFilePersistence:
    def test_top_level_context_with_file_storage_does_not_crash(self, file_storage_singleton):
        # Раньше падало с TypeError, т.к. у file_storage.RequestLog не было
        # полей source/command_name.
        with LogContext("import_users", source="command", command_name="import_users") as col:
            col.add_sql("SELECT 1", duration_ms=1.0)

        logs = file_storage.get_file_storage().all()
        assert len(logs) == 1
        assert logs[0].source == "command"
        assert logs[0].command_name == "import_users"
