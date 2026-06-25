from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeVar

from .collector import Collector, current_collector

F = TypeVar("F", bound=Callable[..., Any])

DEFAULT_SLOW_THRESHOLD_MS: float = 100


class LogContext:
    """Контекстный менеджер для логирования блоков кода.

    Можно использовать как контекстный менеджер или как декоратор.
    При входе создаёт новый ``Collector`` и регистрирует его как текущий.
    При выходе деактивирует коллектор и восстанавливает предыдущий.

    Attributes:
        name: Имя контекста для идентификации в логах.
        slow_threshold_ms: Порог медленных операций в миллисекундах.

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

    Attributes:
        name: Имя контекста.
        slow_threshold_ms: Порог медленных операций.
    """

    def __init__(self, name: str | None = None, slow_threshold_ms: float = DEFAULT_SLOW_THRESHOLD_MS) -> None:
        """Инициализирует контекст логирования.

        Args:
            name: Имя контекста. Если не указано, используется ``None``
                (при декорировании — ``func.__qualname__``).
            slow_threshold_ms: Порог медленных операций в миллисекундах.
                Наследуется от родительского коллектора, если не задан явно.
        """
        self.name: str | None = name
        self.slow_threshold_ms: float = slow_threshold_ms
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
        self._collector = Collector(name=self.name, slow_threshold_ms=slow)
        self._collector.start()
        return self._collector

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Деактивирует коллектор при выходе из контекста.

        Если есть родительский коллектор, все записи дочернего
        переносятся в него, чтобы не потерять данные при сохранении.
        """
        if self._collector:
            child = self._collector
            child.finish()
            parent = current_collector()
            if parent is not None and child is not parent:
                for entry in child.entries:
                    parent.add(entry)

    def __call__(self, func: F) -> F:
        """Декорирует функцию, оборачивая её вызов в контекст логирования.

        Args:
            func: Декорируемая функция.

        Returns:
            Обёрнутая функция с логированием.
        """

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with LogContext(name=self.name or func.__qualname__, slow_threshold_ms=self.slow_threshold_ms):
                return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]
