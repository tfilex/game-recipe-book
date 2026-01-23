# app/routers/recipes.py
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db.models import get_db, User, Recipe
from app.auth import require_auth
from app.schemas import RecipeRequest, RecipeCreate, RecipeUpdate
from app.services.recipe_service import generate_recipe_text

router = APIRouter()


@router.post("/api/recipe")
async def api_generate_recipe(payload: RecipeRequest):
    """
    JSON API для Vue-фронтенда.
    """
    recipe_text = await generate_recipe_text(payload.chat_input)
    return JSONResponse({"recipe": recipe_text})


@router.post("/api/recipes")
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


@router.get("/api/recipes")
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


@router.get("/api/recipes/{recipe_id}")
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


@router.put("/api/recipes/{recipe_id}")
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


@router.delete("/api/recipes/{recipe_id}")
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
