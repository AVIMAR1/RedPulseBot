import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Нет BOT_TOKEN в .env файле!")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./redpulse.db")

# URL для WebApp (локально - localhost, на сервере - домен)
# URL для WebApp
WEBAPP_URL = os.getenv("WEBAPP_URL", "http://127.0.0.1:8000/webapp")