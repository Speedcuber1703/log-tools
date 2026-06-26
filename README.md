# log-tools

Библиотека для Django, которая логирует время выполнения, SQL-запросы и Redis-команды.
Предоставляет HTML-панель для просмотра истории запросов в стиле debug toolbar,
а также standalone HTML-отчёты и management-команду.

## Установка

```bash
pip install log-tools
```

С поддержкой Redis:

```bash
pip install log-tools[redis]
```

С форматированием SQL:

```bash
pip install log-tools[sql]
```

## Быстрый старт

### 1. Middleware (автоматическое логирование всех запросов)

```python
# settings.py
INSTALLED_APPS = [
    ...
    'log_tools',
]

MIDDLEWARE = [
    ...
    'log_tools.middleware.LogToolsMiddleware',
]
```

### 2. Контекстный менеджер

```python
from log_tools import LogContext

def my_view(request):
    with LogContext('загрузка данных') as collector:
        users = list(User.objects.filter(is_active=True))
        products = list(Product.objects.all())

    print(collector.summary())
    # {'name': 'загрузка данных', 'elapsed_ms': 12.3, 'sql_count': 2, ...}
```

### 3. Декоратор

```python
from log_tools import LogContext

@LogContext('мой_view')
def my_view(request):
    data = Product.objects.filter(active=True)
    return JsonResponse({'count': data.count()})
```

### 4. Management команда

```python
# myapp/management/commands/my_task.py
from django.core.management.base import BaseCommand
from log_tools import LogContext

class Command(BaseCommand):
    def handle(self, *args, **options):
        with LogContext('my_task', source='command', command_name='my_task') as collector:
            users = list(User.objects.all())
            collector.add_log('Обработано')
```

```bash
python manage.py my_task
python manage.py log_tools_stats
python manage.py log_tools_stats --html
```

### 5. Панель логов

```python
# urls.py
from log_tools.panel import get_urls

urlpatterns = [
    *get_urls(),
    ...
]
```

Откройте `http://localhost:8000/log-tools/` — таблица истории запросов.

## Настройки

Все настройки задаются через `django.conf.settings`:

| Настройка | По умолчанию | Описание |
|-----------|-------------|----------|
| `LOG_TOOLS_SLOW_THRESHOLD_MS` | `100` | Порог медленных операций в мс. Запросы дольше этого порога помечаются как медленные |
| `LOG_TOOLS_PATCH_DB` | `True` | Автоматически патчить Django для логирования SQL-запросов |
| `LOG_TOOLS_PATCH_REDIS` | `True` | Автоматически патчить redis.Redis для логирования команд |
| `LOG_TOOLS_HISTORY_SIZE` | `100` | Максимальное количество хранимых логов в истории |
| `LOG_TOOLS_FILE_STORAGE` | `False` | Использовать файл для хранения логов (персистентность между перезапусками) |
| `LOG_TOOLS_FILE_PATH` | `None` | Путь к файлу логов. По умолчанию: `log_tools_logs.jsonl` в `BASE_DIR` |
| `LOG_TOOLS_ENABLE_PANEL` | `True` | Включить HTML-панель для просмотра логов |

Пример:

```python
LOG_TOOLS_SLOW_THRESHOLD_MS = 50
LOG_TOOLS_HISTORY_SIZE = 200
LOG_TOOLS_FILE_STORAGE = True
```

## Просмотр статистики

### Через HTTP (при работающем сервере)

| Эндпоинт | Описание |
|----------|----------|
| `/log-tools/` | HTML-панель с историей |
| `/log-tools/?source=file` | Просмотр логов из JSONL-файла |
| `/log-tools/api/` | Текущий/последний лог (JSON) |
| `/log-tools/api/history/?limit=50` | История логов (JSON) |
| `/log-tools/api/<index>/` | Детали конкретного лога (JSON) |
| `/log-tools/api/clear/` | Очистка истории (POST) |

### Через management команду (без сервера)

```bash
# Просмотр в консоли
python manage.py log_tools_stats
python manage.py log_tools_stats --limit 50
python manage.py log_tools_stats --json

# Standalone HTML-отчёт (откроется в браузере)
python manage.py log_tools_stats --html

# Очистка истории
python manage.py log_tools_stats --clear
```

### Файловое хранение (персистентность)

Для использования в management командах и скриптах:

```python
# settings.py
LOG_TOOLS_FILE_STORAGE = True
```

Логи сохраняются в JSONL-файл и доступны после перезапуска приложения.

## Использование в management командах

```python
from django.core.management.base import BaseCommand
from log_tools import LogContext

class Command(BaseCommand):
    def handle(self, *args, **options):
        with LogContext('import_data', source='command', command_name='import_data') as collector:
            # SQL-запросы автоматически логируются
            users = list(User.objects.all())
            collector.add_log(f'Загружено {len(users)} пользователей')

        # Лог автоматически сохраняется в файл
```

```bash
python manage.py import_data
python manage.py log_tools_stats --html  # Откроет HTML-отчёт
```

## Совместимость

| Компонент | Минимальная версия |
|-----------|-------------------|
| Python | 3.8 |
| Django | 3.2 |
| redis (опционально) | 4.0 |

Поддерживаются все версии Django от 3.2 до 5.1. Работает с SQLite, PostgreSQL и MySQL.

## Локальная разработка

```bash
# Клонировать и установить в dev mode
git clone https://github.com/Speedcuber1703/log-tools.git
cd log-tools
pip install -e ".[dev]"

# Запустить тесты
pytest tests/

# Собрать пакет
python -m build

# Отформатировать код
ruff format log_tools/
```

## Лицензия

MIT
