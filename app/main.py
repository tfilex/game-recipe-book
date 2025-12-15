# app/main.py
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import httpx
import uuid
import os
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel
import logging

load_dotenv()

app = FastAPI()

templates = Jinja2Templates(directory="app/templates")

# OpenAI settings (API key must be supplied via environment variable)
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")
if not N8N_WEBHOOK_URL:
    raise RuntimeError("N8N_WEBHOOK_URL environment variable not set")

class RecipeRequest(BaseModel):
    chat_input: str


async def _generate_recipe_text(chat_input: str) -> str:
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
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(N8N_WEBHOOK_URL, json=payload)
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

            # переводы строк для HTML (отображение в браузере)
            if isinstance(recipe_text, str):
                recipe_text = recipe_text.replace("\n", "<br>")
    except Exception as e:
        recipe_text = f"Ошибка: {str(e)}"

    return recipe_text


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "recipe": None})

@app.post("/", response_class=HTMLResponse)
async def generate_recipe(request: Request, chat_input: str = Form(...)):
    recipe_text = await _generate_recipe_text(chat_input)

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "recipe": recipe_text, "chat_input": chat_input}
    )


@app.post("/api/recipe")
async def api_generate_recipe(payload: RecipeRequest):
    """
    JSON API для Vue-фронтенда.
    """
    recipe_text = await _generate_recipe_text(payload.chat_input)
    return JSONResponse({"recipe": recipe_text})