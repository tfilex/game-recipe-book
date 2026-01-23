# app/services/recipe_service.py
import httpx
import uuid
import re
import logging
from typing import cast
from app.config import N8N_WEBHOOK_URL


async def generate_recipe_text(chat_input: str) -> str:
    """
    Вспомогательная функция для запроса в n8n и получения текста рецепта.
    """
    session_id = uuid.uuid4().hex

    # Формируем список объектов как требует n8n
    payload = [
        {
            "sessionId": session_id,
            "action": "sendMessage",
            "chatInput": chat_input,
        }
    ]

    # отладочная информация
    logging.info("Payload отправляется в n8n: %s", payload)
    
    # Проверка наличия URL (должен быть установлен при старте приложения)
    if not N8N_WEBHOOK_URL:
        raise RuntimeError("N8N_WEBHOOK_URL не установлен")
    
    # Type assertion: после проверки N8N_WEBHOOK_URL гарантированно str
    webhook_url = cast(str, N8N_WEBHOOK_URL)
    
    try:
        # Убираем таймаут для долгих запросов
        async with httpx.AsyncClient(timeout=None) as client:
            resp = await client.post(webhook_url, json=payload)
            logging.info("Status code: %s", resp.status_code)
            logging.info("Raw body: %s", resp.text[:500])
            logging.info("Headers: %s", resp.headers)
            resp.raise_for_status()
            try:
                data = resp.json()
            except ValueError as ve:
                logging.error("Ошибка разбора JSON: %s", ve)
                raise
            # ожидаем список с одним объектом вида:
            # [ { "output": "..." } ]
            if isinstance(data, list) and data:
                first = data[0]
                if isinstance(first, dict):
                    # самый частый и желаемый формат
                    if "output" in first and isinstance(first["output"], str):
                        recipe_text = first["output"]
                    # запасной вариант, если n8n завернул в json: { "json": { "output": "..." } }
                    elif "json" in first and isinstance(first["json"], dict) and "output" in first["json"]:
                        recipe_text = str(first["json"]["output"])
                    else:
                        recipe_text = str(first)
                else:
                    recipe_text = str(first)
            elif isinstance(data, dict):
                recipe_text = data.get("output", str(data))
            else:
                recipe_text = str(data)
            
            # Очищаем HTML теги и заменяем <br> на переводы строк
            if isinstance(recipe_text, str):
                # Заменяем <br>, <br/>, <br /> на переводы строк
                recipe_text = re.sub(r'<br\s*\/?>', '\n', recipe_text, flags=re.IGNORECASE)
                # Удаляем другие HTML теги
                recipe_text = re.sub(r'<[^>]+>', '', recipe_text)
                # Декодируем HTML entities если есть
                recipe_text = recipe_text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    except Exception as e:
        recipe_text = f"Ошибка: {str(e)}"

    return recipe_text
