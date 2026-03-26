"""
RedPulseBot Main - Чистая версия v0.1.3
Только работающий код
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, MenuButtonWebApp
from aiogram.exceptions import TelegramForbiddenError

from database import engine, Base, AsyncSessionLocal
from admin import start_admin, init_bot
from bot.handlers import start, profile, tasks, support, announcements, webapp
from bot.keyboards import WEBAPP_URL
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
import os
import json
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Планировщик
scheduler = AsyncIOScheduler()

class DBSessionMiddleware:
    def __init__(self, session_maker):
        self.session_maker = session_maker

    async def __call__(self, handler, event, data):
        async with self.session_maker() as session:
            data["session"] = session
            return await handler(event, data)

class BanCheckMiddleware:
    """Middleware для проверки бана"""
    async def __call__(self, handler, event, data):
        from models import User
        from sqlalchemy import select

        user_id = None
        if hasattr(event, 'from_user') and event.from_user:
            user_id = event.from_user.id
        elif hasattr(event, 'message') and event.message and event.message.from_user:
            user_id = event.message.from_user.id
        elif hasattr(event, 'callback_query') and event.callback_query and event.callback_query.from_user:
            user_id = event.callback_query.from_user.id

        if user_id:
            session = data.get('session')
            if session:
                result = await session.execute(
                    select(User).where(User.telegram_id == user_id)
                )
                user = result.scalar_one_or_none()

                if user and user.is_banned:
                    if user.ban_expires and datetime.fromisoformat(user.ban_expires) < datetime.now():
                        user.is_banned = False
                        user.ban_reason = None
                        user.ban_expires = None
                        await session.commit()
                    else:
                        if hasattr(event, 'text') and event.text and event.text.startswith('/start'):
                            return await handler(event, data)

                        ban_text = f"🚫 <b>Вы забанены!</b>\n\n"
                        if user.ban_reason:
                            ban_text += f"Причина: {user.ban_reason}\n"
                        if user.ban_expires:
                            ban_text += f"Срок: до {datetime.fromisoformat(user.ban_expires).strftime('%d.%m.%Y %H:%M')}"
                        else:
                            ban_text += f"Срок: навсегда"

                        if hasattr(event, 'message') and event.message:
                            await event.message.answer(ban_text)
                        elif hasattr(event, 'callback_query') and event.callback_query:
                            await event.callback_query.message.answer(ban_text)

                        return

        return await handler(event, data)

async def check_banned_users():
    """Проверка разбана"""
    from models import User
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(
                User.is_banned == True,
                User.ban_expires != None,
                User.ban_expires <= datetime.now()
            )
        )
        for user in result.scalars():
            user.is_banned = False
            user.ban_reason = None
            user.ban_expires = None
            try:
                await bot.send_message(user.telegram_id, "✅ <b>Ваш бан истёк!</b>\n\nТы снова можешь пользоваться ботом.", parse_mode="HTML")
                logger.info(f"Пользователь {user.telegram_id} разбанен")
            except Exception as e:
                logger.error(f"Ошибка уведомления о разбане: {e}")
            await session.commit()

async def check_seasons():
    """Проверка начала/окончания сезонов"""
    from models import Season, User
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        now = datetime.now()
        
        # Начавшиеся сезоны
        result = await session.execute(
            select(Season).where(Season.is_active == False, Season.start_date <= now)
        )
        for season in result.scalars():
            season.is_active = True
            await session.commit()
            logger.info(f"Сезон '{season.name}' начался!")

        # Закончившиеся сезоны
        result = await session.execute(
            select(Season).where(Season.is_active == True, Season.end_date <= now)
        )
        for season in result.scalars():
            season.is_active = False
            await session.commit()
            logger.info(f"Сезон '{season.name}' завершён!")

async def check_support_reminders():
    """Напоминания о тикетах"""
    from models import SupportTicket, User
    from sqlalchemy import select, and_

    async with AsyncSessionLocal() as session:
        now = datetime.now()
        result = await session.execute(
            select(SupportTicket).where(
                SupportTicket.status == 'waiting_user',
                SupportTicket.last_activity <= now - timedelta(hours=24),
                SupportTicket.reminder_count < 3
            )
        )
        for ticket in result.scalars():
            user_result = await session.execute(
                select(User).where(User.telegram_id == ticket.user_id)
            )
            user = user_result.scalar_one_or_none()

            if user and not user.is_banned:
                from aiogram.utils.keyboard import InlineKeyboardBuilder
                builder = InlineKeyboardBuilder()
                builder.button(text="✏️ Ответить", callback_data=f"support_ticket_{ticket.id}")

                try:
                    await bot.send_message(
                        ticket.user_id,
                        f"🔔 <b>Напоминание о тикете #{ticket.id}</b>\n\n"
                        f"Мы ждём твоего ответа уже {ticket.reminder_count + 1} день.\n"
                        f"Если не ответить в течение {3 - ticket.reminder_count} дней, тикет будет закрыт.\n\n"
                        f"Нажми кнопку ниже, чтобы ответить:",
                        parse_mode="HTML",
                        reply_markup=builder.as_markup()
                    )
                    ticket.reminder_count += 1
                    logger.info(f"Напоминание отправлено пользователю {ticket.user_id}")
                except Exception as e:
                    logger.error(f"Ошибка отправки напоминания: {e}")

            if ticket.reminder_count >= 3:
                ticket.status = 'closed'
                ticket.closed_at = now
                ticket.closed_by = 'system'
                await session.commit()

async def set_bot_commands():
    """Установка команд бота"""
    commands = [
        BotCommand(command="start", description="🚀 Запустить бота"),
        BotCommand(command="profile", description="👤 Профиль"),
        BotCommand(command="game", description="🎮 Mini App"),
        BotCommand(command="tasks", description="📋 Задания"),
        BotCommand(command="support", description="🆘 Поддержка"),
        BotCommand(command="refresh", description="🔄 Обновить меню"),
    ]
    await bot.set_my_commands(commands)

async def main():
    logger.info("🚀 Запуск main()...")

    # Создаем таблицы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Таблицы БД созданы")

    # Миграции (если нет колонок)
    try:
        import sqlite3
        conn = sqlite3.connect('redpulse.db')
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(users)")
        cols = {row[1] for row in cur.fetchall()}

        def add_col(name, ddl):
            if name not in cols:
                try:
                    cur.execute(f"ALTER TABLE users ADD COLUMN {ddl}")
                    logger.info(f"Добавлена колонка: {name}")
                except Exception:
                    pass

        # Ферма
        add_col("blocks_placed", "INTEGER DEFAULT 0")
        add_col("reactions_triggered", "INTEGER DEFAULT 0")
        add_col("reactor_level", "INTEGER DEFAULT 1")
        add_col("total_energy_produced", "INTEGER DEFAULT 0")
        add_col("farm_state_json", "TEXT")

        # Прогресс
        add_col("level", "INTEGER DEFAULT 1")
        add_col("xp", "INTEGER DEFAULT 0")
        add_col("streak_days", "INTEGER DEFAULT 0")
        add_col("streak_last_date", "TEXT")
        add_col("last_daily_reward_at", "TEXT")

        # Бусты
        add_col("click_power", "INTEGER DEFAULT 1")
        add_col("energy_multiplier", "INTEGER DEFAULT 1")
        add_col("auto_clicker", "INTEGER DEFAULT 0")

        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка миграции: {e}")

    # Регистрация роутеров
    dp.include_router(start.router)
    dp.include_router(profile.router)
    dp.include_router(tasks.router)
    dp.include_router(support.router)
    dp.include_router(announcements.router)
    dp.include_router(webapp.router)

    # Мидлвари
    dp.message.middleware(DBSessionMiddleware(AsyncSessionLocal))
    dp.callback_query.middleware(DBSessionMiddleware(AsyncSessionLocal))
    dp.message.middleware(BanCheckMiddleware())
    dp.callback_query.middleware(BanCheckMiddleware())

    # Планировщик
    scheduler.add_job(check_banned_users, IntervalTrigger(minutes=5), id='bans')
    scheduler.add_job(check_seasons, IntervalTrigger(hours=1), id='seasons')
    scheduler.add_job(check_support_reminders, IntervalTrigger(hours=6), id='support')

    # Команды
    await set_bot_commands()

    # Инициализация админки
    await init_bot(bot)

    # Запуск
    await dp.start_polling(bot)
    scheduler.start()

async def on_shutdown():
    logger.info("Бот останавливается...")
    scheduler.shutdown()
    await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        asyncio.run(on_shutdown())
