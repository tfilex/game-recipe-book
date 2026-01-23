# app/middleware.py
from fastapi import Request
from fastapi.responses import JSONResponse
from app.db.models import SessionLocal
from app.auth import verify_csrf_token
from app.config import CSRF_EXEMPT_PATHS

# Счетчик для периодической очистки сессий
_cleanup_counter = 0


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


async def cleanup_sessions_middleware(request: Request, call_next):
    """Очистка истёкших сессий периодически (каждые 100 запросов)"""
    global _cleanup_counter
    _cleanup_counter += 1
    
    # Очищаем сессии раз в 100 запросов для оптимизации
    if _cleanup_counter % 100 == 0:
        from app.auth import cleanup_expired_sessions
        db = SessionLocal()
        try:
            cleanup_expired_sessions(db)
        except Exception:
            pass
        finally:
            db.close()
    
    response = await call_next(request)
    return response
