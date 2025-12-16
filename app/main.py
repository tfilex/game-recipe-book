# app/main.py
from fastapi import FastAPI, Request, Form, HTTPException, Depends, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import httpx
import uuid
import os
import re
from typing import Optional, List
from dotenv import load_dotenv
from pydantic import BaseModel
import logging

from app.db.models import init_db, get_db, User, Recipe
from app.auth import get_password_hash, authenticate_user, get_current_user, require_auth

load_dotenv()

app = FastAPI()

# Инициализация БД при старте
init_db()

# Статические файлы
import pathlib
static_dir = pathlib.Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

templates = Jinja2Templates(directory="app/templates")

# OpenAI settings (API key must be supplied via environment variable)
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")
if not N8N_WEBHOOK_URL:
    raise RuntimeError("N8N_WEBHOOK_URL environment variable not set")


# Pydantic модели
class RecipeRequest(BaseModel):
    chat_input: str


class RecipeCreate(BaseModel):
    title: str
    content: str
    original_query: Optional[str] = None


class RecipeUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None


class UserRegister(BaseModel):
    username: str
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


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
        # Убираем таймаут для долгих запросов
        async with httpx.AsyncClient(timeout=None) as client:
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


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, user: Optional[User] = Depends(get_current_user)):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "recipe": None,
            "user": user.username if user else None
        }
    )


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


# Аутентификация
@app.post("/api/auth/register")
async def register(user_data: UserRegister, db: Session = Depends(get_db)):
    """Регистрация нового пользователя"""
    # Проверяем, существует ли пользователь
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Пользователь с таким именем уже существует")
    
    # Создаём нового пользователя
    new_user = User(
        username=user_data.username,
        password_hash=get_password_hash(user_data.password)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    response = JSONResponse({"message": "Пользователь успешно зарегистрирован", "username": new_user.username})
    response.set_cookie(key="session_id", value=user_data.username, httponly=True, max_age=86400 * 30)  # 30 дней
    return response


@app.post("/api/auth/login")
async def login(user_data: UserLogin, db: Session = Depends(get_db)):
    """Вход пользователя"""
    user = authenticate_user(db, user_data.username, user_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Неверное имя пользователя или пароль")
    
    response = JSONResponse({"message": "Успешный вход", "username": user.username})
    response.set_cookie(key="session_id", value=user.username, httponly=True, max_age=86400 * 30)  # 30 дней
    return response


@app.post("/api/auth/logout")
async def logout():
    """Выход пользователя"""
    response = JSONResponse({"message": "Выход выполнен"})
    response.delete_cookie(key="session_id")
    return response


@app.get("/api/auth/me")
async def get_me(user: Optional[User] = Depends(get_current_user)):
    """Получить информацию о текущем пользователе"""
    if not user:
        return JSONResponse({"user": None})
    return JSONResponse({"user": {"id": user.id, "username": user.username}})


# Рецепты
@app.post("/api/recipes")
async def create_recipe(
    recipe_data: RecipeCreate,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Создать новый рецепт"""
    new_recipe = Recipe(
        user_id=user.id,
        title=recipe_data.title,
        content=recipe_data.content,
        original_query=recipe_data.original_query
    )
    db.add(new_recipe)
    db.commit()
    db.refresh(new_recipe)
    
    return JSONResponse({
        "id": new_recipe.id,
        "title": new_recipe.title,
        "content": new_recipe.content,
        "created_at": new_recipe.created_at.isoformat()
    })


@app.get("/api/recipes")
async def get_recipes(
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Получить все рецепты пользователя"""
    recipes = db.query(Recipe).filter(Recipe.user_id == user.id).order_by(Recipe.created_at.desc()).all()
    
    return JSONResponse({
        "recipes": [
            {
                "id": r.id,
                "title": r.title,
                "content": r.content,
                "original_query": r.original_query,
                "created_at": r.created_at.isoformat(),
                "updated_at": r.updated_at.isoformat()
            }
            for r in recipes
        ]
    })


@app.get("/api/recipes/{recipe_id}")
async def get_recipe(
    recipe_id: int,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Получить конкретный рецепт"""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id, Recipe.user_id == user.id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Рецепт не найден")
    
    return JSONResponse({
        "id": recipe.id,
        "title": recipe.title,
        "content": recipe.content,
        "original_query": recipe.original_query,
        "created_at": recipe.created_at.isoformat(),
        "updated_at": recipe.updated_at.isoformat()
    })


@app.put("/api/recipes/{recipe_id}")
async def update_recipe(
    recipe_id: int,
    recipe_data: RecipeUpdate,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Обновить рецепт"""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id, Recipe.user_id == user.id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Рецепт не найден")
    
    if recipe_data.title is not None:
        recipe.title = recipe_data.title
    if recipe_data.content is not None:
        recipe.content = recipe_data.content
    
    db.commit()
    db.refresh(recipe)
    
    return JSONResponse({
        "id": recipe.id,
        "title": recipe.title,
        "content": recipe.content,
        "updated_at": recipe.updated_at.isoformat()
    })


@app.delete("/api/recipes/{recipe_id}")
async def delete_recipe(
    recipe_id: int,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Удалить рецепт"""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id, Recipe.user_id == user.id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Рецепт не найден")
    
    db.delete(recipe)
    db.commit()
    
    return JSONResponse({"message": "Рецепт удалён"})
