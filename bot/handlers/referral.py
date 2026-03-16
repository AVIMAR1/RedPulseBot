from aiogram import Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import User

router = Router()

REFERRAL_BONUS = 50

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

@router.message(lambda message: message.text == "👥 Рефералы")
@router.message(Command("ref"))
async def cmd_referral(message: types.Message, session: AsyncSession):
    telegram_id = message.from_user.id
    
    # Получаем пользователя
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        await message.answer("❌ Сначала введите /start")
        return
    
    # Получаем список рефералов
    referrals_result = await session.execute(
        select(User).where(User.referrer_id == telegram_id).order_by(User.created_at.desc())
    )
    referrals = referrals_result.scalars().all()
    
    # Получаем информацию о боте для ссылки
    bot_info = await message.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={telegram_id}"
    
    # Формируем текст
    text = (
        f"👥 <b>Реферальная программа</b>\n\n"
        f"🔗 <b>Твоя ссылка:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• Приглашено друзей: {user.referrals_count}\n"
        f"• Заработано звёзд: {user.referral_bonus} ⭐\n"
        f"• Бонус за друга: {REFERRAL_BONUS} ⭐\n\n"
    )
    
    if referrals:
        text += f"👤 <b>Твои рефералы (последние 5):</b>\n"
        for i, ref in enumerate(referrals[:5], 1):
            name = escape_html(ref.first_name or f"User{ref.telegram_id}")
            date = ref.created_at.strftime('%d.%m.%Y') if ref.created_at else 'неизвестно'
            text += f"{i}. {name} — {date}\n"
    else:
        text += "😢 У тебя пока нет рефералов.\nПоделись ссылкой с друзьями и получай бонусы!"
    
    # Добавляем кнопку для копирования ссылки
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="📋 Выдать ссылку", callback_data=f"copy_ref_{telegram_id}")
    keyboard.adjust(1)
    
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard.as_markup())

@router.callback_query(lambda c: c.data.startswith("copy_ref_"))
async def copy_referral_link(callback: types.CallbackQuery):
    telegram_id = callback.data.split("_")[2]
    bot_info = await callback.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={telegram_id}"
    
    await callback.answer(f"Копируй текст сообщения и делись с друзьями! 📋", show_alert=True)
    await callback.message.answer(f"🎮 Red Pulse — твой личный кликер в Telegram! \n 🔥 Зарабатывай кликая \n ⭐ Получай звёзды рейтинга \n 💎 Участвуй в розыгрышах \n 👇 Жми, тут весело!:\n<code>{ref_link}</code>", parse_mode="HTML")

@router.callback_query(lambda c: c.data == "refresh_ref")
async def refresh_referral(callback: types.CallbackQuery, session: AsyncSession):
    telegram_id = callback.from_user.id
    
    # Получаем обновленные данные
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    referrals_result = await session.execute(
        select(User).where(User.referrer_id == telegram_id).order_by(User.created_at.desc())
    )
    referrals = referrals_result.scalars().all()
    
    bot_info = await callback.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={telegram_id}"
    
    text = (
        f"👥 <b>Реферальная программа</b>\n\n"
        f"🔗 <b>Твоя ссылка:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• Приглашено друзей: {user.referrals_count}\n"
        f"• Заработано звёзд: {user.referral_bonus} ⭐\n"
        f"• Бонус за друга: {REFERRAL_BONUS} ⭐\n\n"
    )
    
    if referrals:
        text += f"👤 <b>Твои рефералы (последние 5):</b>\n"
        for i, ref in enumerate(referrals[:5], 1):
            name = escape_html(ref.first_name or f"User{ref.telegram_id}")
            date = ref.created_at.strftime('%d.%m.%Y') if ref.created_at else 'неизвестно'
            text += f"{i}. {name} — {date}\n"
    else:
        text += "😢 У тебя пока нет рефералов.\nПоделись ссылкой с друзьями и получай бонусы!"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="📋 Копировать ссылку", callback_data=f"copy_ref_{telegram_id}")
    keyboard.button(text="🔄 Обновить", callback_data="refresh_ref")
    keyboard.adjust(1)
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard.as_markup())
    await callback.answer()