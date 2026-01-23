# app/schemas.py
from pydantic import BaseModel, Field, field_validator
from typing import Optional


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
