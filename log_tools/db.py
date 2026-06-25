from __future__ import annotations

import time
from typing import Any

from django.db.backends.utils import CursorWrapper, CursorDebugWrapper


class LoggingCursorWrapper(CursorWrapper):
    """Обёртка над курсором Django, перехватывающая SQL-запросы.

    Перехватывает ``execute()`` и ``executemany()``, измеряет время
    выполнения и записывает информацию в текущий ``Collector``.

    Если активный коллектор отсутствует, запрос выполняется без логирования.
    """

    def execute(self, sql: str, params: Any = None) -> Any:
        """Выполняет SQL-запрос и логирует его в текущий коллектор.

        Args:
            sql: Текст SQL-запроса.
            params: Параметры запроса.

        Returns:
            Результат выполнения запроса.
        """
        from .collector import current_collector

        collector = current_collector()
        if collector is None:
            return super().execute(sql, params)

        start = time.monotonic()
        try:
            return super().execute(sql, params)
        finally:
            duration_ms = (time.monotonic() - start) * 1000
            alias: str = getattr(self.db, "alias", "default")
            collector.add_sql(sql=sql, params=params, duration_ms=duration_ms, alias=alias)

    def executemany(self, sql: str, param_list: Any) -> Any:
        """Выполняет SQL-запрос с множеством параметров и логирует его.

        Args:
            sql: Текст SQL-запроса.
            param_list: Список наборов параметров.

        Returns:
            Результат выполнения запроса.
        """
        from .collector import current_collector

        collector = current_collector()
        if collector is None:
            return super().executemany(sql, param_list)

        start = time.monotonic()
        try:
            return super().executemany(sql, param_list)
        finally:
            duration_ms = (time.monotonic() - start) * 1000
            alias: str = getattr(self.db, "alias", "default")
            collector.add_sql(
                sql=f"{sql} [x{len(param_list)}]",
                params=None,
                duration_ms=duration_ms,
                alias=alias,
            )


class LoggingCursorDebugWrapper(LoggingCursorWrapper, CursorDebugWrapper):
    """Обёртка для отладочного курсора Django с логированием.

    Наследует логирование от ``LoggingCursorWrapper`` и
    отладочные возможности от ``CursorDebugWrapper``.
    """


_ORIGINAL_DB_MODULES: dict[str, type] = {}


def patch_db() -> None:
    """Заменяет ``CursorWrapper`` и ``CursorDebugWrapper`` Django на логирующие версии.

    Патчит ``django.db.backends.utils`` и бэкенды конкретных СУБД
    (PostgreSQL, MySQL и др.), так как они определяют собственные
    подклассы ``CursorDebugWrapper``.

    Вызывается автоматически из ``LogToolsConfig.ready()``
    если настройка ``LOG_TOOLS_PATCH_DB = True``.
    """
    import django.db.backends.utils as utils

    utils.CursorWrapper = LoggingCursorWrapper  # type: ignore[assignment]
    utils.CursorDebugWrapper = LoggingCursorDebugWrapper  # type: ignore[assignment]

    _patch_db_backend("django.db.backends.postgresql.base")
    _patch_db_backend("django.db.backends.mysql.base")
    _patch_db_backend("django.db.backends.sqlite3.base")


def _patch_db_backend(module_path: str) -> None:
    """Патчит ``CursorDebugWrapper`` в конкретном бэкенде СУБД.

    Args:
        module_path: Путь к модулю бэкенда (например,
            ``django.db.backends.postgresql.base``).
    """
    import importlib

    try:
        backend_module = importlib.import_module(module_path)
    except (ImportError, Exception):
        return

    if hasattr(backend_module, "CursorDebugWrapper"):
        _ORIGINAL_DB_MODULES[module_path] = backend_module.CursorDebugWrapper
        backend_module.CursorDebugWrapper = LoggingCursorDebugWrapper  # type: ignore[assignment]


def unpatch_db() -> None:
    """Восстанавливает оригинальные ``CursorWrapper`` и ``CursorDebugWrapper`` Django.

    Используется для отключения логирования или в тестах.
    """
    import django.db.backends.utils as utils

    utils.CursorWrapper = CursorWrapper  # type: ignore[assignment]
    utils.CursorDebugWrapper = CursorDebugWrapper  # type: ignore[assignment]

    for module_path, original_class in _ORIGINAL_DB_MODULES.items():
        import importlib

        try:
            backend_module = importlib.import_module(module_path)
            backend_module.CursorDebugWrapper = original_class  # type: ignore[assignment]
        except (ImportError, Exception):
            pass

    _ORIGINAL_DB_MODULES.clear()
