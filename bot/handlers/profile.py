from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models import User
from bot.keyboards import WEBAPP_URL
from core.progression import progress_for_xp, render_progress_bar
import json
import os

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
    """Получает статистику из фермы (Mini App) - данные из БД"""
    try:
        import sqlite3
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
                'total_energy': row['total_energy_produced'] or 0,
                'blocks_placed': row['blocks_placed'] or 0,
                'reactions_triggered': row['reactions_triggered'] or 0
            }
        
        return {
            'reactor_level': 1,
            'total_energy': 0,
            'blocks_placed': 0,
            'reactions_triggered': 0
        }
    except Exception as e:
        print(f"Error getting farm stats: {e}")
        return {
            'reactor_level': 1,
            'total_energy': 0,
            'blocks_placed': 0,
            'reactions_triggered': 0
        }


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
    
    # Получаем общую сумму рефералов из БД
    total_referrals_result = await session.execute(
        select(func.count(User.id)).where(User.referrer_id == telegram_id)
    )
    total_referrals = total_referrals_result.scalar() or 0

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
    
    # Статистика фермы
    farm_stats = get_farm_stats(telegram_id)
    
    # Уровень ядра и игрока
    core_level = farm_stats['reactor_level'] or 1
    player_level = ((core_level - 1) // 5) + 1

    profile_text = (
        f"👤 <b>Твой профиль</b>\n\n"
        f"🆔 ID: <code>{safe_telegram_id}</code>\n"
        f"📛 Имя: {safe_first_name or 'Не указано'}\n"
        f"👤 Username: @{safe_username or 'Не указан'}\n\n"
        f"🏅 <b>Уровень игрока:</b> {player_level}\n"
        f"⚛️ <b>Уровень ядра:</b> {core_level}\n"
        f"⭐ XP: {prog['xp']} ({prog['xp_in_level']}/{prog['xp_to_next']})\n"
        f"{bar} {prog['pct']}%\n\n"
        f"💰 <b>Валюты:</b>\n"
        f"🪙 Монеты: {user.click_coins:,}\n"
        f"⭐ RED PULSE STARS: {user.stars:,}\n"
        f"💎 Кристаллы: {user.crystals:,}\n\n"
        f"⚛️ <b>Ферма (Реактор):</b>\n"
        f"🧱 Блоков установлено: {farm_stats['blocks_placed']}\n"
        f"💥 Реакций запущено: {farm_stats['reactions_triggered']}\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"👥 Рефералов: {total_referrals}\n"
        f"📋 Заданий выполнено: {user.tasks_completed}\n"
        f"🖱️ Всего действий: {user.total_clicks:,}\n"
        f"⚡ Сила клика: x{user.click_power}\n\n"
        f"🔥 <b>Streak:</b> {streak_days} дн.\n\n"
        f"📅 В боте с: {user.created_at.strftime('%d.%m.%Y') if user.created_at else 'Неизвестно'}"
    )

    # Кнопки для обновления и открытия Mini App
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить профиль", callback_data="refresh_profile")],
        [InlineKeyboardButton(text="🎮 Открыть ферму в Mini App", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])

    await message.answer(profile_text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(lambda c: c.data == "refresh_profile")
async def refresh_profile(callback: types.CallbackQuery, session: AsyncSession):
    """Обновление профиля"""
    await callback.answer("Профиль обновлён!", show_alert=True)
    await cmd_profile(callback.message, session)
