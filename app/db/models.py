# app/db/models.py
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime, timezone
import os

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.now(timezone.utc))

    recipes = relationship("Recipe", back_populates="owner", cascade="all, delete-orphan")


class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    original_query = Column(String)
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    owner = relationship("User", back_populates="recipes")


class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_token = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    csrf_token = Column(String, nullable=True)  # CSRF токен для защиты от CSRF атак
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=False)

    user = relationship("User")


# Путь к БД (в папке db, не в репозитории)
DB_DIR = os.path.join(os.path.dirname(__file__))
DB_PATH = os.path.join(DB_DIR, "recipes.db")

# Создаём движок SQLite
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

# Создаём сессию
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Создаёт все таблицы в БД и выполняет миграции"""
    Base.metadata.create_all(bind=engine)
    
    # Миграция: добавление колонки csrf_token в таблицу sessions
    inspector = inspect(engine)
    if 'sessions' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('sessions')]
        if 'csrf_token' not in columns:
            # Добавляем колонку csrf_token
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE sessions ADD COLUMN csrf_token VARCHAR"))
                conn.commit()
            print("Миграция: добавлена колонка csrf_token в таблицу sessions")


def get_db():
    """Получить сессию БД"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

