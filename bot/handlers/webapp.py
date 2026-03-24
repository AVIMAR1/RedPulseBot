from aiogram import Router, types
from aiogram.filters import Command
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import User
from bot.keyboards import WEBAPP_URL

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

    # Отправляем кнопку для открытия Mini App
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
    
    await message.answer(
        f"🎮 <b>Red Pulse Clicker</b>\n\n"
        f"Кликай и зарабатывай монеты!\n"
        f"🪙 Твои монеты: {user.click_coins}\n"
        f"💎 Звёзды: {user.stars}\n\n"
        f"Нажми кнопку ниже чтобы открыть игру:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎮 Открыть игру", web_app=WebAppInfo(url=WEBAPP_URL))]
        ])
    )