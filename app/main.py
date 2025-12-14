# app/main.py
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import httpx
import uuid
import os
from typing import Optional
from dotenv import load_dotenv
import logging

load_dotenv()

app = FastAPI()

templates = Jinja2Templates(directory="app/templates")

# OpenAI settings (API key must be supplied via environment variable)
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")
if not N8N_WEBHOOK_URL:
    raise RuntimeError("N8N_WEBHOOK_URL environment variable not set")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "recipe": None})

@app.post("/", response_class=HTMLResponse)
async def generate_recipe(request: Request, chat_input: str = Form(...)):
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
            # ожидаем список с одним объектом {"output": "..."}
            if isinstance(data, list) and data:
                recipe_text = data[0].get("output", str(data))
            elif isinstance(data, dict):
                recipe_text = data.get("output", str(data))
            else:
                recipe_text = str(data)
            # переводы строк для HTML
            recipe_text = recipe_text.replace("\n", "<br>")
    except Exception as e:
        recipe_text = f"Ошибка: {str(e)}"

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "recipe": recipe_text, "chat_input": chat_input}
    )