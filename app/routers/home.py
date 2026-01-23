# app/routers/home.py
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Optional

from app.db.models import User
from app.auth import get_current_user
from app.services.recipe_service import generate_recipe_text

router = APIRouter()

templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, user: Optional[User] = Depends(get_current_user)):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "recipe": None,
            "user": user.username if user else None
        }
    )


@router.post("/", response_class=HTMLResponse)
async def generate_recipe(request: Request, chat_input: str = Form(...)):
    recipe_text = await generate_recipe_text(chat_input)

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "recipe": recipe_text, "chat_input": chat_input}
    )
