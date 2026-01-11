# app/auth.py
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
import bcrypt
import secrets
from datetime import datetime, timedelta
from typing import Optional
from app.db.models import get_db, User, Session as SessionModel


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
    """Аутентификация пользователя с защитой от timing attacks"""
    # Всегда выполняем проверку пароля, даже если пользователь не найден
    # Это защищает от timing attacks (утечки информации о существовании пользователя)
    dummy_hash = "$2b$12$" + "0" * 53  # Dummy bcrypt hash для постоянного времени выполнения
    
    user = db.query(User).filter(User.username == username).first()
    password_hash = user.password_hash if user else dummy_hash
    
    # Всегда проверяем пароль для постоянного времени выполнения
    is_valid = verify_password(password, password_hash)
    
    if not user or not is_valid:
        return False
    return user


def create_session(db: Session, user_id: int, days: int = 30) -> tuple[str, str]:
    """Создать новую сессию для пользователя. Возвращает (session_token, csrf_token)"""
    # Генерируем безопасный токен сессии
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    
    # Создаём сессию в БД
    expires_at = datetime.utcnow() + timedelta(days=days)
    session = SessionModel(
        session_token=session_token,
        user_id=user_id,
        csrf_token=csrf_token,
        expires_at=expires_at
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    
    return session_token, csrf_token


def get_session_user(db: Session, session_token: str) -> User | None:
    """Получить пользователя по токену сессии"""
    if not session_token:
        return None
    
    # Ищем активную сессию
    session = db.query(SessionModel).filter(
        SessionModel.session_token == session_token,
        SessionModel.expires_at > datetime.utcnow()
    ).first()
    
    if not session:
        return None
    
    # Возвращаем пользователя
    return db.query(User).filter(User.id == session.user_id).first()


def delete_session(db: Session, session_token: str) -> None:
    """Удалить сессию"""
    if not session_token:
        return
    
    session = db.query(SessionModel).filter(
        SessionModel.session_token == session_token
    ).first()
    
    if session:
        db.delete(session)
        db.commit()


def cleanup_expired_sessions(db: Session) -> None:
    """Очистить истёкшие сессии"""
    db.query(SessionModel).filter(
        SessionModel.expires_at <= datetime.utcnow()
    ).delete()
    db.commit()


def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Получить текущего пользователя из сессии"""
    session_token = request.cookies.get("session_id")
    if not session_token:
        return None
    
    return get_session_user(db, session_token)


def require_auth(request: Request, db: Session = Depends(get_db)):
    """Требовать аутентификацию"""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация"
        )
    return user


# CSRF защита
def generate_csrf_token(db: Session, session_token: str) -> str:
    """Генерировать CSRF токен для сессии и сохранить в БД"""
    csrf_token = secrets.token_urlsafe(32)
    
    # Обновляем CSRF токен в БД
    session = db.query(SessionModel).filter(
        SessionModel.session_token == session_token,
        SessionModel.expires_at > datetime.utcnow()
    ).first()
    
    if session:
        session.csrf_token = csrf_token
        db.commit()
    
    return csrf_token


def get_csrf_token(db: Session, session_token: str) -> Optional[str]:
    """Получить CSRF токен для сессии из БД"""
    if not session_token:
        return None
    
    session = db.query(SessionModel).filter(
        SessionModel.session_token == session_token,
        SessionModel.expires_at > datetime.utcnow()
    ).first()
    
    if not session:
        return None
    
    return session.csrf_token


def verify_csrf_token(db: Session, session_token: str, csrf_token: str) -> bool:
    """Проверить CSRF токен"""
    if not session_token or not csrf_token:
        return False
    
    session = db.query(SessionModel).filter(
        SessionModel.session_token == session_token,
        SessionModel.expires_at > datetime.utcnow()
    ).first()
    
    if not session or not session.csrf_token:
        return False
    
    # Используем constant-time сравнение для защиты от timing attacks
    return secrets.compare_digest(session.csrf_token, csrf_token)


def delete_csrf_token(db: Session, session_token: str) -> None:
    """Удалить CSRF токен при выходе"""
    session = db.query(SessionModel).filter(
        SessionModel.session_token == session_token
    ).first()
    
    if session:
        session.csrf_token = None
        db.commit()

