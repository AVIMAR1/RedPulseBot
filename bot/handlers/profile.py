from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import User
from bot.keyboards import WEBAPP_URL
from core.progression import progress_for_xp, render_progress_bar

router = Router()

def escape_html(text):
    """Экранирует все специальные символы HTML"""
    if text is None:
        return ""
    text = str(text)
    html_escape_table = {
        "&": "&amp;",
        '"': "&quot;",
        "'": "&apos;",
        ">": "&gt;",
        "<": "&lt;",
    }
    for char, escape in html_escape_table.items():
        text = text.replace(char, escape)
    return text


@router.message(lambda message: message.text == "👤 Профиль")
@router.message(Command("profile"))
async def cmd_profile(message: types.Message, session: AsyncSession):
    telegram_id = message.from_user.id

    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    if not user:
        await message.answer("❌ Сначала введите /start")
        return

    # Считаем рефералов
    referrals_result = await session.execute(
        select(User).where(User.referrer_id == telegram_id)
    )
    referrals = referrals_result.scalars().all()
    referrals_count = len(referrals)

    # Экранируем данные
    safe_first_name = escape_html(user.first_name)
    safe_username = escape_html(user.username)
    safe_telegram_id = escape_html(str(user.telegram_id))

    # Прогресс/уровни
    xp = int(getattr(user, "xp", 0) or 0)
    if xp <= 0:
        xp = int(user.total_clicks or 0)
    prog = progress_for_xp(xp)
    bar = render_progress_bar(prog["pct"], width=12)

    # Streak
    streak_days = int(getattr(user, "streak_days", 0) or 0)

    profile_text = (
        f"👤 <b>Твой профиль</b>\n\n"
        f"🆔 ID: <code>{safe_telegram_id}</code>\n"
        f"📛 Имя: {safe_first_name or 'Не указано'}\n"
        f"👤 Username: @{safe_username or 'Не указан'}\n\n"
        f"🏅 <b>Уровень:</b> {prog['level']}\n"
        f"⭐ XP: {prog['xp']} ({prog['xp_in_level']}/{prog['xp_to_next']})\n"
        f"{bar} {prog['pct']}%\n\n"
        f"💰 <b>Валюты:</b>\n"
        f"🪙 Клик-монеты: {user.click_coins}\n"
        f"⭐ RED PULSE STARS: {user.stars}\n"
        f"💎 Кристаллы: {user.crystals}\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"👥 Рефералов: {referrals_count}\n"
        f"🖱️ Всего кликов: {user.total_clicks}\n"
        f"📋 Заданий выполнено: {user.tasks_completed}\n"
        f"⚡ Сила клика: x{user.click_power}\n\n"
        f"🔥 <b>Streak:</b> {streak_days} дн.\n\n"
        f"📅 В боте с: {user.created_at.strftime('%d.%m.%Y %H:%M') if user.created_at else 'Неизвестно'}"
    )

    # Кнопка для открытия полного профиля в Mini App
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Полный профиль в Mini App", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])

    await message.answer(profile_text, parse_mode="HTML", reply_markup=keyboard)
