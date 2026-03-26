from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import User
from bot.keyboards import WEBAPP_URL
import sqlite3

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


def get_farm_stats(telegram_id):
    """Получает статистику фермы из БД"""
    try:
        conn = sqlite3.connect('redpulse.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT reactor_level, blocks_placed, reactions_triggered, total_energy_produced
            FROM users WHERE telegram_id = ?
        """, (telegram_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                'reactor_level': row['reactor_level'] or 1,
                'blocks_placed': row['blocks_placed'] or 0,
                'reactions_triggered': row['reactions_triggered'] or 0,
                'total_energy_produced': row['total_energy_produced'] or 0
            }
        return {'reactor_level': 1, 'blocks_placed': 0, 'reactions_triggered': 0, 'total_energy_produced': 0}
    except Exception as e:
        print(f"Error getting farm stats: {e}")
        return {'reactor_level': 1, 'blocks_placed': 0, 'reactions_triggered': 0, 'total_energy_produced': 0}


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
    total_referrals = len(referrals)

    # Экранируем данные
    safe_first_name = escape_html(user.first_name)
    safe_username = escape_html(user.username)

    # Статистика фермы из БД
    farm_stats = get_farm_stats(telegram_id)
    core_level = farm_stats['reactor_level'] or 1
    player_level = ((core_level - 1) // 5) + 1

    profile_text = (
        f"👤 <b>Твой профиль</b>\n\n"
        f"📛 <b>Имя:</b> {safe_first_name or 'Не указано'}\n"
        f"👤 <b>Username:</b> @{safe_username or 'Не указан'}\n\n"
        f"🏅 <b>Уровень игрока:</b> {player_level}\n"
        f"⚛️ <b>Уровень ядра:</b> {core_level}\n\n"
        f"💰 <b>Валюты:</b>\n"
        f"🪙 Монеты: {user.click_coins:,}\n"
        f"⭐ Звёзды: {user.stars:,}\n"
        f"💎 Кристаллы: {user.crystals:,}\n\n"
        f"⚛️ <b>Ферма (Реактор):</b>\n"
        f"🧱 Блоков: {farm_stats['blocks_placed']}\n"
        f"💥 Реакций: {farm_stats['reactions_triggered']:,}\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"👥 Рефералов: {total_referrals}\n"
        f"📋 Заданий: {user.tasks_completed}\n"
        f"🔥 Streak: {user.streak_days} дн.\n\n"
        f"📅 В боте с: {user.created_at.strftime('%d.%m.%Y') if user.created_at else 'Неизвестно'}"
    )

    # Кнопка для открытия Mini App
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Открыть ферму", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])

    await message.answer(profile_text, parse_mode="HTML", reply_markup=keyboard)
