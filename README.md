# Game Recipe Book

Небольшое веб-приложение на **FastAPI**, которое генерирует «рецепт по игре» на основе текстового запроса (например, названия игры, сеттинга или персонажей).

## Возможности

- **Веб-интерфейс** с формой для ввода запроса (рендеринг на сервере через Jinja2).
- **Интеграция с n8n** через webhook для генерации рецептов.
- Простая и понятная структура кода.

## Требования

- Python 3.12+
- Зависимости из `pyproject.toml` (установятся автоматически)

## Установка

1. Клонируйте репозиторий:
   ```bash
   git clone <repository-url>
   cd game-recipe-book
   ```

2. Создайте и активируйте виртуальное окружение:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # На Windows: .venv\Scripts\activate
   ```

3. Установите зависимости:
   ```bash
   pip install -e .
   ```

   Или с использованием `uv`:
   ```bash
   uv sync
   ```

## Настройка

1. Создайте файл `.env` в корне проекта:
   ```env
   N8N_WEBHOOK_URL=https://ваш-n8n-сервер/webhook/ваш-id
   ```

## Запуск

```bash
uvicorn app.main:app --reload
```

Приложение будет доступно по адресу: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

## Структура проекта

```
game-recipe-book/
├── app/
│   ├── __init__.py
│   ├── main.py           # Основное приложение FastAPI
│   └── templates/
│       └── index.html    # HTML-шаблон
├── backend/              # Дополнительный FastAPI-сервис (пример)
├── pyproject.toml        # Зависимости и настройки проекта
└── README.md             # Этот файл
```

## Разработка

- Для разработки с автоматической перезагрузкой:
  ```bash
  uvicorn app.main:app --reload
  ```

## Лицензия

MIT © 2025 Dudolin Deins. См. файл [LICENSE](LICENSE).