# app/main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import pathlib

from app.db.models import init_db
from app.middleware import csrf_protection_middleware, cleanup_sessions_middleware
from app.routers import home, auth, recipes

# Создание приложения FastAPI
app = FastAPI()

# Инициализация БД при старте
init_db()

# Регистрация middleware (порядок важен: CSRF protection должен быть первым)
@app.middleware("http")
async def csrf_middleware(request, call_next):
    return await csrf_protection_middleware(request, call_next)

@app.middleware("http")
async def cleanup_middleware(request, call_next):
    return await cleanup_sessions_middleware(request, call_next)

# Статические файлы
static_dir = pathlib.Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Регистрация роутеров
app.include_router(home.router)
app.include_router(auth.router)
app.include_router(recipes.router)
