from __future__ import annotations

from typing import Any

from django.conf import settings


def get_setting(name: str, default: Any = None) -> Any:
    """Читает настройку из ``django.conf.settings``.

    Args:
        name: Имя настройки.
        default: Значение по умолчанию, если настройка не задана.

    Returns:
        Значение настройки или ``default``.
    """
    return getattr(settings, name, default)


LOG_TOOLS_SLOW_THRESHOLD_MS: float = get_setting("LOG_TOOLS_SLOW_THRESHOLD_MS", 100)
"""Порог медленных операций в миллисекундах. Операции дольше этого порога считаются медленными."""

LOG_TOOLS_PATCH_DB: bool = get_setting("LOG_TOOLS_PATCH_DB", True)
"""Автоматически патчить ``CursorWrapper`` для логирования SQL-запросов."""

LOG_TOOLS_PATCH_REDIS: bool = get_setting("LOG_TOOLS_PATCH_REDIS", True)
"""Автоматически патчить ``redis.Redis`` для логирования команд."""

LOG_TOOLS_ENABLE_PANEL: bool = get_setting("LOG_TOOLS_ENABLE_PANEL", True)
"""Включить HTML-панель для просмотра логов."""

LOG_TOOLS_HISTORY_SIZE: int = get_setting("LOG_TOOLS_HISTORY_SIZE", 100)
"""Максимальное количество хранимых логов в истории (кольцевой буфер)."""
