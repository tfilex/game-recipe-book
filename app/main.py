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
from pydantic import BaseModel, Field, field_validator
import logging

from app.db.models import init_db, get_db, User, Recipe, SessionLocal
from app.auth import (
    get_password_hash, 
    authenticate_user, 
    get_current_user, 
    require_auth,
    create_session,
    delete_session,
    cleanup_expired_sessions,
    generate_csrf_token,
    get_csrf_token,
    verify_csrf_token,
    delete_csrf_token
)

load_dotenv()

app = FastAPI()

# Инициализация БД при старте
init_db()

# Middleware для очистки истёкших сессий (оптимизировано: раз в 100 запросов)
_cleanup_counter = 0

# Список путей, которые не требуют CSRF защиты
CSRF_EXEMPT_PATHS = {
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/me",
    "/api/auth/csrf-token",
    "/api/recipe",  # Публичный эндпоинт генерации рецептов
    "/",
    "/static",
}

@app.middleware("http")
async def csrf_protection_middleware(request: Request, call_next):
    """Проверка CSRF токенов для изменяющих запросов"""
    # Безопасные методы не требуют CSRF защиты
    if request.method in ("GET", "HEAD", "OPTIONS"):
        response = await call_next(request)
        return response
    
    # Проверяем, не является ли путь исключением
    path = request.url.path
    if any(path.startswith(exempt) for exempt in CSRF_EXEMPT_PATHS):
        response = await call_next(request)
        return response
    
    # Получаем session token из cookie
    session_token = request.cookies.get("session_id")
    
    # Если нет сессии, пропускаем (будет обработано require_auth)
    if not session_token:
        response = await call_next(request)
        return response
    
    # Получаем CSRF токен из заголовка
    csrf_token = request.headers.get("X-CSRF-Token")
    
    # Проверяем CSRF токен через БД
    db = SessionLocal()
    try:
        if not csrf_token or not verify_csrf_token(db, session_token, csrf_token):
            return JSONResponse(
                {"detail": "Неверный CSRF токен"},
                status_code=403
            )
    finally:
        db.close()
    
    response = await call_next(request)
    return response


@app.middleware("http")
async def cleanup_sessions_middleware(request: Request, call_next):
    """Очистка истёкших сессий периодически (каждые 100 запросов)"""
    global _cleanup_counter
    _cleanup_counter += 1
    
    # Очищаем сессии раз в 100 запросов для оптимизации
    if _cleanup_counter % 100 == 0:
        db = SessionLocal()
        try:
            cleanup_expired_sessions(db)
        except Exception:
            pass
        finally:
            db.close()
    
    response = await call_next(request)
    return response

# Статические файлы
import pathlib
static_dir = pathlib.Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

templates = Jinja2Templates(directory="app/templates")

# OpenAI settings (API key must be supplied via environment variable)
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")
if not N8N_WEBHOOK_URL:
    raise RuntimeError("N8N_WEBHOOK_URL environment variable not set")

# Настройки безопасности
# В production должно быть True (требует HTTPS)
# В development можно False для работы через HTTP
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"


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
    username: str = Field(..., min_length=3, max_length=50, pattern="^[a-zA-Z0-9_]+$")
    password: str = Field(..., min_length=8, max_length=128)
    
    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Имя пользователя не может быть пустым")
        return v.strip()
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Пароль не может быть пустым")
        return v


class UserLogin(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=128)


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
    
    # Создаём сессию для нового пользователя (возвращает session_token и csrf_token)
    session_token, csrf_token = create_session(db, new_user.id, days=30)
    
    response = JSONResponse({
        "message": "Пользователь успешно зарегистрирован", 
        "username": new_user.username,
        "csrf_token": csrf_token
    })
    response.set_cookie(
        key="session_id", 
        value=session_token, 
        httponly=True, 
        secure=COOKIE_SECURE,  # Только через HTTPS (в production)
        max_age=86400 * 30,  # 30 дней
        samesite="lax",
        path="/"
    )
    # CSRF токен в отдельной cookie (не httpOnly, чтобы JS мог его читать)
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,  # JS должен иметь доступ для отправки в заголовке
        secure=COOKIE_SECURE,
        max_age=86400 * 30,
        samesite="lax",
        path="/"
    )
    return response


@app.post("/api/auth/login")
async def login(user_data: UserLogin, db: Session = Depends(get_db)):
    """Вход пользователя"""
    user = authenticate_user(db, user_data.username, user_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Неверное имя пользователя или пароль")
    
    # Создаём сессию для пользователя (возвращает session_token и csrf_token)
    session_token, csrf_token = create_session(db, user.id, days=30)
    
    response = JSONResponse({
        "message": "Успешный вход", 
        "username": user.username,
        "csrf_token": csrf_token
    })
    response.set_cookie(
        key="session_id", 
        value=session_token, 
        httponly=True, 
        secure=COOKIE_SECURE,  # Только через HTTPS (в production)
        max_age=86400 * 30,  # 30 дней
        samesite="lax",
        path="/"
    )
    # CSRF токен в отдельной cookie (не httpOnly, чтобы JS мог его читать)
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,  # JS должен иметь доступ для отправки в заголовке
        secure=COOKIE_SECURE,
        max_age=86400 * 30,
        samesite="lax",
        path="/"
    )
    return response


@app.post("/api/auth/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    """Выход пользователя"""
    session_token = request.cookies.get("session_id")
    if session_token:
        delete_session(db, session_token)
        delete_csrf_token(db, session_token)
    
    response = JSONResponse({"message": "Выход выполнен"})
    response.delete_cookie(key="session_id")
    response.delete_cookie(key="csrf_token")
    return response


@app.get("/api/auth/me")
async def get_me(request: Request, user: Optional[User] = Depends(get_current_user), db: Session = Depends(get_db)):
    """Получить информацию о текущем пользователе"""
    if not user:
        return JSONResponse({"user": None, "csrf_token": None})
    
    session_token = request.cookies.get("session_id")
    csrf_token = get_csrf_token(db, session_token) if session_token else None
    
    # Если CSRF токен отсутствует, генерируем новый
    if session_token and not csrf_token:
        csrf_token = generate_csrf_token(db, session_token)
    
    response = JSONResponse({
        "user": {"id": user.id, "username": user.username},
        "csrf_token": csrf_token
    })
    
    # Обновляем cookie с CSRF токеном, если он был сгенерирован
    if csrf_token and session_token:
        response.set_cookie(
            key="csrf_token",
            value=csrf_token,
            httponly=False,
            secure=COOKIE_SECURE,
            max_age=86400 * 30,
            samesite="lax",
            path="/"
        )
    
    return response


@app.get("/api/auth/csrf-token")
async def get_csrf_token_endpoint(request: Request, user: Optional[User] = Depends(get_current_user), db: Session = Depends(get_db)):
    """Получить CSRF токен для текущей сессии"""
    if not user:
        return JSONResponse({"csrf_token": None}, status_code=401)
    
    session_token = request.cookies.get("session_id")
    if not session_token:
        return JSONResponse({"csrf_token": None}, status_code=401)
    
    csrf_token = get_csrf_token(db, session_token)
    
    # Если токен отсутствует, генерируем новый
    if not csrf_token:
        csrf_token = generate_csrf_token(db, session_token)
    
    response = JSONResponse({"csrf_token": csrf_token})
    # Обновляем cookie с CSRF токеном
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=COOKIE_SECURE,
        max_age=86400 * 30,
        samesite="lax",
        path="/"
    )
    return response


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
