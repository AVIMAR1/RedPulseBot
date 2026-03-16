from aiogram import Router, types
from aiogram.filters import Command
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import User
from core.config import WEBAPP_URL

router = Router()

@router.message(Command("game"))
async def cmd_game(message: types.Message, session: AsyncSession):
    """Открывает мини-приложение (кликер)"""
    telegram_id = message.from_user.id
    
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        await message.answer("❌ Сначала введите /start")
        return
    
    # Вместо кнопки отправляем прямую ссылку
    webapp_url = "http://127.0.0.1:8000/webapp"
    
    await message.answer(
        f"🎮 **Red Pulse Clicker**\n\n"
        f"Кликай и зарабатывай монеты!\n"
        f"🪙 Твои монеты: {user.coins}\n"
        f"💎 Звёзды: {user.stars}\n\n"
        f"🔗 **Ссылка для теста:**\n{webapp_url}\n\n"
        f"✨ Открой её в браузере (или web.telegram.org)",
        parse_mode="Markdown"
    )