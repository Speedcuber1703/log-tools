# log-tools

Библиотека для Django, которая логирует время выполнения, SQL-запросы и Redis-команды. Предоставляет HTML-панель для просмотра истории запросов в стиле debug toolbar.

## Установка

```bash
pip install log-tools
```

С поддержкой Redis:

```bash
pip install log-tools[redis]
```

## Быстрый старт

### 1. Middleware (автоматическое логирование всех запросов)

Добавьте `LogToolsMiddleware` в `MIDDLEWARE` и `log_tools` в `INSTALLED_APPS`:

```python
# settings.py

INSTALLED_APPS = [
    ...
    "log_tools",
]

MIDDLEWARE = [
    ...
    "log_tools.middleware.LogToolsMiddleware",
]
```

Middleware автоматически перехватывает SQL-запросы и Redis-команды для каждого HTTP-запроса.

### 2. Контекстный менеджер (логирование конкретных блоков)

```python
from log_tools import LogContext

def my_view(request):
    with LogContext("загрузка данных") as collector:
        users = list(User.objects.all())
        cache.set("users", users)

    print(collector.summary())
    # {'name': 'загрузка данных', 'elapsed_ms': 12.3, 'sql_count': 1, ...}
```

### 3. Декоратор

```python
from log_tools import LogContext

@LogContext("мой_view")
def my_view(request):
    data = Product.objects.filter(active=True)
    return JsonResponse({"count": data.count()})
```

### 4. Панель логов

```python
# urls.py
from log_tools.panel import get_urls

urlpatterns = [
    *get_urls(),
    ...
]
```

Откройте `http://localhost:8000/log-tools/` — увидите таблицу истории запросов с SQL, Redis и таймингами.

## Настройки

Все настройки задаются через `django.conf.settings`:

| Настройка | По умолчанию | Описание |
|-----------|-------------|----------|
| `LOG_TOOLS_SLOW_THRESHOLD_MS` | `100` | Порог медленных операций в мс. Запросы дольше этого порога помечаются как медленные |
| `LOG_TOOLS_PATCH_DB` | `True` | Автоматически патчить Django для логирования SQL-запросов |
| `LOG_TOOLS_PATCH_REDIS` | `True` | Автоматически патчить redis.Redis для логирования команд |
| `LOG_TOOLS_HISTORY_SIZE` | `100` | Количество хранимых логов в истории (кольцевой буфер) |
| `LOG_TOOLS_ENABLE_PANEL` | `True` | Включить HTML-панель для просмотра логов |

Пример:

```python
LOG_TOOLS_SLOW_THRESHOLD_MS = 50
LOG_TOOLS_HISTORY_SIZE = 200
```

## Панель логов

### HTML-панель

Доступна по адресу `/log-tools/`. Показывает:

- Таблицу истории всех запросов с HTTP-методом, путём, статусом, временем выполнения
- Количество SQL-запросов и Redis-команд для каждого запроса
- Детальный просмотр при клике на строку (полный список SQL, Redis, таймингов)
- SQL-запросы отформатированы через `sqlparse`

### JSON API

| Эндпоинт | Метод | Описание |
|----------|-------|----------|
| `/log-tools/api/` | GET | Текущий или последний лог |
| `/log-tools/api/history/` | GET | История логов (параметр `?limit=N`) |
| `/log-tools/api/<index>/` | GET | Детали конкретного лога по индексу |
| `/log-tools/api/clear/` | POST | Очистка истории |

Запросы к самому инструменту (`/log-tools/*`) не попадают в историю.

## Использование вручную

### Логирование SQL

```python
from log_tools import LogContext

with LogContext("db操作") as collector:
    list(User.objects.filter(is_active=True))
    list(Product.objects.all())

# Все SQL-запроси автоматически попадают в collector
print(collector.summary()["sql_count"])  # 2
```

### Логирование Redis

```python
import redis
from log_tools import LogContext

r = redis.Redis()

with LogContext("cache") as collector:
    r.set("key", "value")
    r.get("key")

print(collector.summary()["redis_count"])  # 2
```

### Ручное добавление записей

```python
from log_tools import LogContext

with LogContext("manual") as collector:
    collector.add_log("Начало обработки")
    collector.add_timing("этап_1", 5.2)
    collector.add_sql("SELECT 1", duration_ms=1.0)
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
git clone https://github.com/ponomarev/log-tools.git
cd log-tools
pip install -e ".[dev]"

# Запустить тесты
pytest tests/

# Собрать пакет
python -m build
```

## Лицензия

MIT
