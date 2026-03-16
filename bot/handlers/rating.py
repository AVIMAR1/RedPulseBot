from aiogram import Router, types
from aiogram.filters import Command
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.utils.keyboard import InlineKeyboardBuilder

from models import User, Season, SeasonRating
from bot.keyboards import rating_menu
from datetime import datetime

router = Router()

@router.message(lambda message: message.text == "🏆 Рейтинг")
@router.message(Command("rating"))
async def cmd_rating(message: types.Message, session: AsyncSession):
    # Получаем активный сезон
    now = datetime.now()
    season_result = await session.execute(
        select(Season).where(
            Season.is_active == True,
            Season.start_date <= now,
            Season.end_date > now
        )
    )
    season = season_result.scalar_one_or_none()
    
    if season:
        # Рейтинг текущего сезона
        rating_result = await session.execute(
            select(User)
            .order_by(desc(User.stars))
            .limit(10)
        )
        top_users = rating_result.scalars().all()
        
        text = f"🏆 **Сезон: {season.name}**\n\n"
        text += f"📅 До конца: {(season.end_date - now).days} дней\n\n"
        text += "**Топ-10 пользователей:**\n"
        
        for i, user in enumerate(top_users, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🔹"
            name = user.first_name or f"User{user.telegram_id}"
            text += f"{medal} {i}. {name} — {user.stars} ⭐\n"
        
        if season.prize_1st:
            text += f"\n🎁 **Призы сезона:**\n"
            text += f"🥇 1 место: {season.prize_1st}\n"
            if season.prize_2nd:
                text += f"🥈 2 место: {season.prize_2nd}\n"
            if season.prize_3rd:
                text += f"🥉 3 место: {season.prize_3rd}\n"
        
        # Позиция пользователя
        user_result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = user_result.scalar_one_or_none()
        
        if user:
            # Считаем место пользователя
            all_users = await session.execute(
                select(User).order_by(desc(User.stars))
            )
            all_users_list = all_users.scalars().all()
            user_rank = next((i for i, u in enumerate(all_users_list, 1) if u.telegram_id == user.telegram_id), None)
            
            if user_rank:
                text += f"\n📊 Твоя позиция: {user_rank} место ({user.stars} ⭐)"
        
    else:
        # Общий рейтинг за всё время
        rating_result = await session.execute(
            select(User)
            .order_by(desc(User.stars))
            .limit(10)
        )
        top_users = rating_result.scalars().all()
        
        text = "🏆 **Общий рейтинг за всё время**\n\n"
        
        for i, user in enumerate(top_users, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🔹"
            name = user.first_name or f"User{user.telegram_id}"
            text += f"{medal} {i}. {name} — {user.stars} ⭐\n"
    
    await message.answer(text, parse_mode="Markdown", reply_markup=rating_menu())

@router.callback_query(lambda c: c.data == "rating_top")
async def rating_top(callback: types.CallbackQuery, session: AsyncSession):
    rating_result = await session.execute(
        select(User)
        .order_by(desc(User.stars))
        .limit(10)
    )
    top_users = rating_result.scalars().all()
    
    text = "🏆 **Топ-10 пользователей:**\n\n"
    
    for i, user in enumerate(top_users, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🔹"
        name = user.first_name or f"User{user.telegram_id}"
        text += f"{medal} {i}. {name} — {user.stars} ⭐\n"
    
    await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(lambda c: c.data == "rating_seasons")
async def rating_seasons(callback: types.CallbackQuery, session: AsyncSession):
    now = datetime.now()
    seasons_result = await session.execute(
        select(Season).order_by(desc(Season.start_date))
    )
    seasons = seasons_result.scalars().all()
    
    if not seasons:
        await callback.answer("❌ Нет сезонов")
        return
    
    builder = InlineKeyboardBuilder()
    for season in seasons:
        status = "✅" if season.is_active else "📅"
        builder.button(
            text=f"{status} {season.name}",
            callback_data=f"season_{season.id}"
        )
    
    builder.adjust(1)
    
    await callback.message.edit_text(
        "📅 **Список сезонов:**\n"
        "Выбери сезон для просмотра результатов:",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


def _parse_season_date(value):
    """Приводит дату из БД к datetime для отображения."""
    if value is None:
        return None
    if hasattr(value, "strftime"):
        return value
    s = str(value).strip().replace("T", " ")[:19]
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            return datetime.strptime(s[:16], "%Y-%m-%d %H:%M")
        except ValueError:
            return None


@router.callback_query(lambda c: c.data and c.data.startswith("season_"))
async def rating_season_detail(callback: types.CallbackQuery, session: AsyncSession):
    """Просмотр результатов выбранного сезона (текущего или прошлого)."""
    try:
        season_id = int(callback.data.split("_")[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка", show_alert=True)
        return
    
    season_result = await session.execute(select(Season).where(Season.id == season_id))
    season = season_result.scalar_one_or_none()
    
    if not season:
        await callback.answer("Сезон не найден", show_alert=True)
        return
    
    # Топ-10 по звёздам (общий рейтинг — исторического среза по сезону нет)
    rating_result = await session.execute(
        select(User)
        .where(User.is_banned == False)
        .order_by(desc(User.stars))
        .limit(10)
    )
    top_users = rating_result.scalars().all()
    
    start_str = ""
    end_str = ""
    if season.start_date:
        start_dt = _parse_season_date(season.start_date)
        if start_dt:
            start_str = start_dt.strftime("%d.%m.%Y")
    if season.end_date:
        end_dt = _parse_season_date(season.end_date)
        if end_dt:
            end_str = end_dt.strftime("%d.%m.%Y")
    
    text = f"🏆 **{season.name}**\n\n"
    if season.description:
        text += f"{season.description}\n\n"
    text += f"📅 Период: {start_str} — {end_str}\n"
    if season.is_active:
        text += "🟢 **Сезон идёт**\n\n"
    else:
        text += "📦 **Сезон завершён (архив)**\n\n"
    
    text += "**Топ-10 по звёздам:**\n"
    for i, user in enumerate(top_users, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🔹"
        name = user.first_name or f"User{user.telegram_id}"
        text += f"{medal} {i}. {name} — {user.stars} ⭐\n"
    
    if season.prize_1st or season.prize_2nd or season.prize_3rd:
        text += "\n🎁 **Призы:**\n"
        if season.prize_1st:
            text += f"🥇 {season.prize_1st}\n"
        if season.prize_2nd:
            text += f"🥈 {season.prize_2nd}\n"
        if season.prize_3rd:
            text += f"🥉 {season.prize_3rd}\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Сезоны", callback_data="rating_seasons")
    builder.button(text="🏆 Топ-10", callback_data="rating_top")
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())
    await callback.answer()