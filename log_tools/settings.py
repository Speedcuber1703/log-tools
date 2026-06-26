"""Ленивые настройки библиотеки log-tools.

Все настройки читаются из ``django.conf.settings`` при обращении,
а не при импорте модуля. Это позволяет переопределять их
в ``settings.py`` проекта без проблем с порядком импорта.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings as _django_settings


class _Settings:
    """Ленивый прокси для чтения настроек из ``django.conf.settings``.

    Каждое обращение к атрибуту читает значение из Django settings
    в реальном времени, что позволяет переопределять настройки
    в ``settings.py`` проекта.

    Example:
        В ``settings.py`` проекта::

            LOG_TOOLS_SLOW_THRESHOLD_MS = 50
            LOG_TOOLS_FILE_STORAGE = True

        В коде::

            from log_tools.settings import LOG_TOOLS

            threshold = LOG_TOOLS.SLOW_THRESHOLD_MS  # 50
    """

    def _get(self, name: str, default: Any = None) -> Any:
        """Читает настройку из ``django.conf.settings``.

        Args:
            name: Имя настройки (без префикса ``LOG_TOOLS_``).
            default: Значение по умолчанию.

        Returns:
            Значение настройки или ``default``.
        """
        full_name = f'LOG_TOOLS_{name}'
        return getattr(_django_settings, full_name, default)

    @property
    def SLOW_THRESHOLD_MS(self) -> float:
        """Порог медленных операций в миллисекундах.

        Операции дольше этого порога считаются медленными.
        По умолчанию: 100 мс.
        """
        return self._get('SLOW_THRESHOLD_MS', 100)

    @property
    def PATCH_DB(self) -> bool:
        """Автоматически патчить ``CursorWrapper`` для логирования SQL-запросов.

        По умолчанию: ``True``.
        """
        return self._get('PATCH_DB', True)

    @property
    def PATCH_REDIS(self) -> bool:
        """Автоматически патчить ``redis.Redis`` для логирования команд.

        По умолчанию: ``True``.
        """
        return self._get('PATCH_REDIS', True)

    @property
    def ENABLE_PANEL(self) -> bool:
        """Включить HTML-панель для просмотра логов.

        По умолчанию: ``True``.
        """
        return self._get('ENABLE_PANEL', True)

    @property
    def HISTORY_SIZE(self) -> int:
        """Максимальное количество хранимых логов в истории.

        По умолчанию: 100.
        """
        return self._get('HISTORY_SIZE', 100)

    @property
    def FILE_STORAGE(self) -> bool:
        """Использовать файл для хранения логов.

        Включает персистентность между перезапусками.
        По умолчанию: ``False``.
        """
        return self._get('FILE_STORAGE', False)

    @property
    def FILE_PATH(self) -> str | None:
        """Путь к файлу логов.

        По умолчанию: ``None`` (используется ``log_tools_logs.jsonl`` в ``BASE_DIR``).
        """
        return self._get('FILE_PATH', None)


LOG_TOOLS = _Settings()
