"""Контекстный менеджер для логирования блоков кода.

Предоставляет ``LogContext`` для использования как контекстный менеджер
или декоратор. Автоматически сохраняет логи в файл при отсутствии
родительского коллектора.
"""

from __future__ import annotations

import types
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from .collector import Collector, Source, current_collector

F = TypeVar('F', bound=Callable[..., Any])

DEFAULT_SLOW_THRESHOLD_MS: float = 1000


class LogContext:
    """Контекстный менеджер для логирования блоков кода.

    Можно использовать как контекстный менеджер или как декоратор.
    При входе создаёт новый ``Collector`` и регистрирует его как текущий.
    При выходе деактивирует коллектор и восстанавливает предыдущий.

    Attributes:
        name: Имя контекста для идентификации в логах.
        slow_threshold_ms: Порог медленных операций в миллисекундах.
        source: Источник логов (HTTP или COMMAND).
        command_name: Имя management-команды.

    Example:
        Использование как контекстный менеджер::

            with LogContext("загрузка данных") as collector:
                data = fetch_from_db()
                cache.set("key", data)

            print(collector.summary())

        Использование как декоратор::

            @LogContext("мой_view")
            def my_view(request):
                ...
    """

    def __init__(
        self,
        name: str | None = None,
        slow_threshold_ms: float = DEFAULT_SLOW_THRESHOLD_MS,
        source: Source = Source.HTTP,
        command_name: str | None = None,
    ) -> None:
        """Инициализирует контекст логирования.

        Args:
            name: Имя контекста. Если не указано, используется ``None``
                (при декорировании — ``func.__qualname__``).
            slow_threshold_ms: Порог медленных операций в миллисекундах.
                Наследуется от родительского коллектора, если не задан явно.
            source: Источник логов (HTTP или COMMAND).
            command_name: Имя management-команды.
        """
        self.name: str | None = name
        self.slow_threshold_ms: float = slow_threshold_ms
        self.source: Source = Source(source) if isinstance(source, str) else source
        self.command_name: str | None = command_name
        self._collector: Collector | None = None

    def __enter__(self) -> Collector:
        """Создаёт и активирует коллектор при входе в контекст.

        Если уже есть активный коллектор, наследует его ``slow_threshold_ms``.

        Returns:
            Созданный ``Collector``.
        """
        parent = current_collector()
        slow = self.slow_threshold_ms
        if parent and slow == DEFAULT_SLOW_THRESHOLD_MS:
            slow = parent.slow_threshold_ms
        self._collector = Collector(
            name=self.name,
            slow_threshold_ms=slow,
            source=self.source,
            command_name=self.command_name,
        )
        self._collector.start()
        return self._collector

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Деактивирует коллектор при выходе из контекста.

        Если есть родительский коллектор, все записи дочернего
        переносятся в него. Если родителя нет и включено файловое
        хранение — сохраняет лог в файл.
        """
        if self._collector:
            child = self._collector
            child.finish()
            parent = current_collector()
            if parent is not None and child is not parent:
                for entry in child.entries:
                    parent.add(entry)
            elif parent is None:
                self._save_to_file(child)

    def _save_to_file(self, collector: Collector) -> None:
        """Сохраняет коллектор в файловое хранилище.

        Вызывается при отсутствии родительского коллектора
        и включённой настройке ``LOG_TOOLS_FILE_STORAGE``.
        """
        from .settings import LOG_TOOLS

        if not LOG_TOOLS.FILE_STORAGE:
            return

        from .file_storage import get_file_storage, RequestLog
        from ._serialization import serialize_entry

        parts = collector.name.split(' ', 1)
        method = collector.command_name or (parts[0] if parts else '')
        path = parts[1] if len(parts) > 1 else collector.name

        storage = get_file_storage()
        log = RequestLog(
            method=method,
            path=path,
            status_code=200,
            elapsed_ms=collector.elapsed_ms(),
            summary=collector.summary(),
            entries=[serialize_entry(entry) for entry in collector.entries],
            source=collector.source,
            command_name=collector.command_name,
        )
        storage.add(log)

    def __call__(self, func: F) -> F:
        """Декорирует функцию, оборачивая её вызов в контекст логирования.

        Args:
            func: Декорируемая функция.

        Returns:
            Обёрнутая функция с логированием.
        """

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with LogContext(
                name=self.name or func.__qualname__,
                slow_threshold_ms=self.slow_threshold_ms,
                source=self.source,
                command_name=self.command_name,
            ):
                return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]
