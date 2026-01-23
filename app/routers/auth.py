# app/routers/auth.py
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional

from app.db.models import get_db, User
from app.auth import (
    get_password_hash,
    authenticate_user,
    get_current_user,
    create_session,
    delete_session,
    generate_csrf_token,
    get_csrf_token,
    delete_csrf_token
)
from app.schemas import UserRegister, UserLogin
from app.config import COOKIE_SECURE

router = APIRouter()


@router.post("/api/auth/register")
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


@router.post("/api/auth/login")
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


@router.post("/api/auth/logout")
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


@router.get("/api/auth/me")
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


@router.get("/api/auth/csrf-token")
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
