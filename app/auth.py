# app/auth.py
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
import bcrypt
from app.db.models import get_db, User


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверка пароля"""
    try:
        # Проверяем пароль с помощью bcrypt
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Хеширование пароля"""
    # Ограничение bcrypt: пароль не должен быть длиннее 72 байта
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]
    
    # Генерируем соль и хешируем пароль
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def authenticate_user(db: Session, username: str, password: str):
    """Аутентификация пользователя"""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return False
    if not verify_password(password, user.password_hash):
        return False
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Получить текущего пользователя из сессии"""
    session_id = request.cookies.get("session_id")
    if not session_id:
        return None
    
    # Простая проверка: ищем пользователя по session_id (в реальном приложении нужна таблица сессий)
    # Для простоты используем username как session_id
    user = db.query(User).filter(User.username == session_id).first()
    return user


def require_auth(request: Request, db: Session = Depends(get_db)):
    """Требовать аутентификацию"""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация"
        )
    return user

