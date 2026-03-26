import os
import random
import logging
from datetime import datetime, timedelta
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import User, Case, UserCase, GlobalBank
from bot.keyboards import main_menu, REFERRAL_BONUS, WEBAPP_URL
from core.progression import progress_for_xp

router = Router()
logger = logging.getLogger(__name__)

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


def _date_only(dt):
    if not dt:
        return None
    if hasattr(dt, "date"):
        try:
            return dt.date()
        except Exception:
            return None
    try:
        return datetime.fromisoformat(str(dt)).date()
    except Exception:
        return None


def apply_daily_login_rewards(user: User) -> dict:
    """Обновляет streak и выдаёт ежедневную награду."""
    now = datetime.now()
    today = now.date()
    yesterday = today - timedelta(days=1)

    last_streak_date = _date_only(getattr(user, "streak_last_date", None))
    last_daily = _date_only(getattr(user, "last_daily_reward_at", None))

    if last_streak_date != today:
        if last_streak_date == yesterday:
            user.streak_days = int(getattr(user, "streak_days", 0) or 0) + 1
        else:
            user.streak_days = 1
        user.streak_last_date = now

    streak_days = int(getattr(user, "streak_days", 0) or 0)

    if last_daily == today:
        return {"given": False, "streak_days": streak_days}

    coins = 100 + min(streak_days, 10) * 25
    xp = 10 + min(streak_days, 30) * 5
    crystals = 1 if random.random() < 0.05 else 0

    user.click_coins = int(user.click_coins or 0) + coins
    user.xp = int(getattr(user, "xp", 0) or 0) + xp
    user.level = progress_for_xp(int(user.xp or 0))["level"]
    if crystals:
        user.crystals = int(user.crystals or 0) + crystals

    user.last_daily_reward_at = now

    return {"given": True, "streak_days": streak_days, "coins": coins, "xp": xp, "crystals": crystals}


def apply_random_bonus(user: User) -> dict:
    """Рандомные бонусы при входе."""
    now = datetime.now()
    last = getattr(user, "last_random_bonus_at", None)
    try:
        if last and hasattr(last, "timestamp"):
            if (now - last) < timedelta(hours=6):
                return {"given": False}
    except Exception:
        pass

    chance = 0.04
    if random.random() >= chance:
        return {"given": False}

    roll = random.random()
    coins = 0
    xp = 0
    crystals = 0
    if roll < 0.70:
        coins = random.randint(50, 250)
    elif roll < 0.92:
        xp = random.randint(20, 80)
    else:
        crystals = 1

    if coins:
        user.click_coins = int(user.click_coins or 0) + coins
    if xp:
        user.xp = int(getattr(user, "xp", 0) or 0) + xp
        user.level = progress_for_xp(int(user.xp or 0))["level"]
    if crystals:
        user.crystals = int(user.crystals or 0) + crystals

    user.last_random_bonus_at = now
    return {"given": True, "coins": coins, "xp": xp, "crystals": crystals}


@router.message(Command("start"))
async def cmd_start(message: types.Message, session: AsyncSession):
    logger.info(f"📩 /start получен от {message.from_user.id}")
    telegram_id = message.from_user.id

    referrer_id = None
    args = message.text.split()
    if len(args) > 1:
        try:
            referrer_id = int(args[1])
            if referrer_id == telegram_id:
                referrer_id = None
        except ValueError:
            referrer_id = None

    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    safe_first_name = escape_html(message.from_user.first_name)

    if not user:
        # Новый пользователь
        user = User(
            telegram_id=telegram_id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            referrer_id=referrer_id
        )
        session.add(user)

        if referrer_id:
            result = await session.execute(select(User).where(User.telegram_id == referrer_id))
            referrer = result.scalar_one_or_none()

            if referrer:
                referrer.referrals_count += 1
                case_result = await session.execute(select(Case).where(Case.name == "Реферальный кейс").limit(1))
                ref_case = case_result.scalar_one_or_none()
                if ref_case:
                    session.add(UserCase(user_id=referrer_id, case_id=ref_case.id, count=1))
                    session.add(UserCase(user_id=telegram_id, case_id=ref_case.id, count=1))
                
                safe_referrer_name = escape_html(referrer.first_name)
                await message.bot.send_message(
                    referrer_id,
                    f"🎉 По твоей ссылке зарегистрировался {safe_referrer_name}!\n🎁 Ты получил <b>кейс</b>!",
                    parse_mode="HTML"
                )

        await session.commit()

        # Награды при первом входе
        daily = apply_daily_login_rewards(user)
        bonus = apply_random_bonus(user)
        await session.commit()

        # Формируем приветственное сообщение
        bot_info = await message.bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start={telegram_id}"

        welcome_text = (
            f"👋 <b>Добро пожаловать в Red Pulse!</b>\n\n"
            f"🎮 <b>Red Pulse</b> — это современный кликер с элементами казино, магазином и системой достижений.\n\n"
            f"💰 <b>Твои стартовые валюты:</b>\n"
            f"🪙 Клик-монеты: {user.click_coins}\n"
            f"⭐ RED PULSE STARS: {user.stars}\n"
            f"💎 Кристаллы: {user.crystals}\n\n"
            f"🚀 <b>Что дальше?</b>\n"
            f"1️⃣ Нажми кнопку <b>🎮 Red Pulse Game</b> ниже, чтобы начать игру!\n"
            f"2️⃣ Приглашай друзей: {ref_link}\n"
            f"3️⃣ Выполняй задания и получай бонусы!\n\n"
            f"🎁 <b>Бонусы за рефералов:</b>\n"
            f"• За каждого друга — кейс с наградами\n"
            f"• Звёзды для повышения в рейтинге\n\n"
            f"📋 <b>Используй кнопки ниже для навигации:</b>"
        )

        # Добавляем текст о ежедневной награде
        if daily.get("given"):
            welcome_text += (
                f"\n\n🎁 <b>Ежедневная награда!</b>\n"
                f"🔥 Streak: {daily.get('streak_days', 1)} дн.\n"
                f"🪙 +{daily.get('coins', 0)} | ⭐ XP +{daily.get('xp', 0)}"
                + (f" | 💎 +{daily.get('crystals', 0)}" if daily.get('crystals') else "")
            )

        if bonus.get("given"):
            welcome_text += (
                f"\n\n🌿 <b>Случайный бонус!</b>\n"
                f"🪙 +{bonus.get('coins', 0)}"
                + (f" ⭐ XP +{bonus.get('xp', 0)}" if bonus.get('xp') else "")
                + (f" 💎 +{bonus.get('crystals', 0)}" if bonus.get('crystals') else "")
            )

        await message.answer(welcome_text, parse_mode="HTML", reply_markup=main_menu())

    else:
        # Повторный вход
        daily = apply_daily_login_rewards(user)
        bonus = apply_random_bonus(user)
        await session.commit()

        extra = ""
        if daily.get("given"):
            extra = (
                f"\n\n🎁 <b>Ежедневная награда!</b>\n"
                f"🔥 Streak: {daily.get('streak_days', 0)} дн.\n"
                f"🪙 +{daily.get('coins', 0)} | ⭐ XP +{daily.get('xp', 0)}"
                + (f" | 💎 +{daily.get('crystals', 0)}" if daily.get('crystals') else "")
            )
        if bonus.get("given"):
            extra += (
                f"\n\n🌿 <b>Случайный бонус!</b>\n"
                f"🪙 +{bonus.get('coins', 0)}"
                + (f" ⭐ XP +{bonus.get('xp', 0)}" if bonus.get('xp') else "")
                + (f" 💎 +{bonus.get('crystals', 0)}" if bonus.get('crystals') else "")
            )

        await message.answer(
            f"👋 <b>С возвращением, {safe_first_name}!</b>\n\n"
            f"💰 <b>Твой баланс:</b>\n"
            f"🪙 Монеты: {user.click_coins}\n"
            f"⭐ Звёзды: {user.stars}\n"
            f"💎 Кристаллы: {user.crystals}\n"
            f"👥 Рефералов: {user.referrals_count}\n"
            f"🔥 Streak: {user.streak_days} дн."
            f"{extra}\n\n"
            f"🎮 <b>Нажми кнопку ниже, чтобы открыть игру!</b>",
            parse_mode="HTML",
            reply_markup=main_menu()
        )


@router.message(Command("game"))
async def cmd_game(message: types.Message):
    """Открыть Mini App через команду /game"""
    await message.answer(
        "🎮 <b>Red Pulse Mini App</b>\n\n"
        "Нажми кнопку ниже, чтобы открыть игру:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎮 Открыть игру", web_app=WebAppInfo(url=WEBAPP_URL))]
        ])
    )


@router.message(lambda m: m.text and m.text.strip() == "🎮 Red Pulse Game")
async def open_mini_app(message: types.Message):
    """Обработка нажатия кнопки Mini App"""
    # Telegram сам откроет WebApp, этот хендлер для совместимости
    pass

@router.message(Command("refresh"))
async def cmd_refresh(message: types.Message):
    """Принудительное обновление меню бота"""
    await message.answer(
        "🔄 <b>Меню обновлено!</b>\n\n"
        "Если кнопки не работают:\n"
        "1️⃣ Закройте и откройте бота заново\n"
        "2️⃣ Нажмите на три точки → Обновить\n"
        "3️⃣ Введите команду заново\n\n"
        "🎮 <b>Кнопки меню:</b>\n"
        "• /start - Главное меню\n"
        "• /profile - Профиль\n"
        "• /game - Открыть игру\n"
        "• /tasks - Задания\n"
        "• /support - Поддержка",
        parse_mode="HTML"
    )


@router.message(Command("cleardb"))
async def cmd_cleardb(message: types.Message):
    """Очистка localStorage (для тестирования)"""
    await message.answer(
        "🧹 <b>Очистка данных</b>\n\n"
        "Для очистки localStorage в Mini App:\n"
        "1. Откройте ферму\n"
        "2. Введите в консоли браузера:\n"
        "<code>window.clearLocalData()</code>\n\n"
        "Или просто закройте и откройте бота заново.",
        parse_mode="HTML"
    )
