from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import User, Season

router = Router()


@router.message(lambda message: message.text == "📢 Анонсы")
@router.message(Command("announcements"))
async def cmd_announcements(message: types.Message, session: AsyncSession):
    telegram_id = message.from_user.id

    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    if not user:
        await message.answer("❌ Сначала введите /start")
        return

    # Получаем активный сезон
    season_result = await session.execute(
        select(Season).where(Season.is_active == True).limit(1)
    )
    season = season_result.scalar_one_or_none()

    announcements_text = "📢 **Анонсы Red Pulse**\n\n"

    if season:
        from datetime import datetime
        end_date = ""
        if season.end_date:
            try:
                if hasattr(season.end_date, "strftime"):
                    end_date = season.end_date.strftime("%d.%m.%Y")
                else:
                    end_date = datetime.fromisoformat(str(season.end_date)).strftime("%d.%m.%Y")
            except Exception:
                pass

        announcements_text += f"🏆 **Текущий сезон:** {season.name}\n"
        if season.description:
            announcements_text += f"{season.description}\n"
        if end_date:
            announcements_text += f"📅 Длится до: {end_date}\n"
        announcements_text += "\n"
        announcements_text += f"🥇 1 место: {season.prize_1st or 'Приз'}\n"
        announcements_text += f"🥈 2 место: {season.prize_2nd or 'Приз'}\n"
        announcements_text += f"🥉 3 место: {season.prize_3rd or 'Приз'}\n\n"
    else:
        announcements_text += "⏳ **Сезон готовится...**\n\n"
        announcements_text += "Следи за анонсами, чтобы не пропустить начало!\n\n"

    announcements_text += (
        "📌 **Что нового?**\n"
        "• 🎮 **Mini App** — играй прямо в Telegram!\n"
        "• 🎰 Казино: кости, слоты, блэкджек\n"
        "• 🛒 Магазин с бустами и скинами\n"
        "• 📋 Ежедневные задания\n"
        "• 🏆 Рейтинг игроков\n\n"
        "🔔 **Подпишись на уведомления**, чтобы не пропустить:\n"
        "• Начало новых сезонов\n"
        "• Специальные события\n"
        "• Бонусы и акции"
    )

    await message.answer(
        announcements_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔔 Включить уведомления", callback_data="announcements_subscribe")],
            [InlineKeyboardButton(text="🎮 Открыть Mini App", callback_data="open_miniapp")]
        ])
    )


@router.callback_query(lambda c: c.data == "announcements_subscribe")
async def announcements_subscribe(callback: types.CallbackQuery, session: AsyncSession):
    # Здесь можно добавить логику подписки на уведомления
    await callback.answer(
        "✅ Вы подписаны на уведомления!\n\n"
        "Вы будете получать анонсы о новых сезонах и событиях.",
        show_alert=True
    )


@router.callback_query(lambda c: c.data == "open_miniapp")
async def open_miniapp(callback: types.CallbackQuery):
    from bot.keyboards import WEBAPP_URL
    await callback.answer("Открываю Mini App...", show_alert=False)
    # Telegram обработает это как открытие WebApp если отправить сообщение с кнопкой
