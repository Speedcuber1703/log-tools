from django.apps import AppConfig


class LogToolsConfig(AppConfig):
    """Django-приложение log_tools.

    Автоматически патчит DB и Redis при старте Django,
    если соответствующие настройки включены.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "log_tools"
    verbose_name = "Log Tools"

    def ready(self) -> None:
        """Вызывается Django после загрузки всех приложений.

        Применяет патчи для DB и Redis в соответствии с настройками.
        """
        from .settings import LOG_TOOLS

        if LOG_TOOLS.PATCH_DB:
            from .db import patch_db

            patch_db()

        if LOG_TOOLS.PATCH_REDIS:
            try:
                from .redis import patch_redis

                patch_redis()
            except ImportError:
                pass
