# app/config.py
import os
from dotenv import load_dotenv

load_dotenv()

# N8N Webhook URL для генерации рецептов
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")
if not N8N_WEBHOOK_URL:
    raise RuntimeError("N8N_WEBHOOK_URL environment variable not set")

# Настройки безопасности
# В production должно быть True (требует HTTPS)
# В development можно False для работы через HTTP
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

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
