from __future__ import annotations

import time
from typing import Any

try:
    import redis as redis_lib
except ImportError:
    redis_lib = None


def _create_logging_redis_class() -> type[Any] | None:
    """Создаёт подкласс ``redis.Redis`` с перехватом команд.

    Переопределяет ``execute_command()`` для логирования имени команды,
    аргументов и времени выполнения в текущий ``Collector``.

    Returns:
        Подкласс ``redis.Redis`` или ``None`` если библиотека ``redis`` не установлена.
    """
    if redis_lib is None:
        return None

    from .collector import current_collector

    class LoggingRedis(redis_lib.Redis):
        """Redis-клиент с автоматическим логированием команд.

        Логирует каждую команду, переданную через ``execute_command()``,
        в текущий ``Collector`` (если он активен).
        """

        def execute_command(self, *args: Any, **options: Any) -> Any:
            """Выполняет Redis-команду и логирует её.

            Args:
                *args: Аргументы команды (первый — имя команды).
                **options: Дополнительные параметры подключения.

            Returns:
                Результат выполнения команды.
            """
            collector = current_collector()
            if collector is None:
                return super().execute_command(*args, **options)

            command: str = str(args[0]) if args else 'UNKNOWN'
            cmd_args: tuple[Any, ...] = args[1:] if len(args) > 1 else ()

            start = time.monotonic()
            try:
                return super().execute_command(*args, **options)
            finally:
                duration_ms: float = (time.monotonic() - start) * 1000
                collector.add_redis(
                    command=command,
                    args=cmd_args,
                    duration_ms=duration_ms,
                )

    return LoggingRedis


_logging_redis_class: type[Any] | None = None


def get_logging_redis_class() -> type[Any] | None:
    """Возвращает класс ``LoggingRedis`` (синглтон).

    Создаёт класс при первом вызове, в дальнейшем возвращает кэшированный.

    Returns:
        Подкласс ``redis.Redis`` с логированием или ``None``.
    """
    global _logging_redis_class
    if _logging_redis_class is None:
        _logging_redis_class = _create_logging_redis_class()
    return _logging_redis_class


def patch_redis() -> None:
    """Заменяет ``redis.Redis`` на ``LoggingRedis``.

    Вызывается автоматически из ``LogToolsConfig.ready()``
    если настройка ``LOG_TOOLS_PATCH_REDIS = True``.
    Ничего не делает, если библиотека ``redis`` не установлена.
    """
    if redis_lib is None:
        return
    cls = get_logging_redis_class()
    if cls is not None:
        redis_lib.Redis = cls  # type: ignore[assignment]


def unpatch_redis() -> None:
    """Восстанавливает оригинальный ``redis.Redis``.

    Используется для отключения логирования или в тестах.
    """
    if redis_lib is None:
        return
    from redis import Redis

    redis_lib.Redis = Redis  # type: ignore[assignment]
