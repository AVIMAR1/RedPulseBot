"""
RedPulseBot Main v0.1.3 - РАБОЧАЯ ВЕРСИЯ
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from aiogram.filters import Command

from database import engine, Base, AsyncSessionLocal
from admin import start_admin, init_bot
from bot.handlers import start, profile, tasks, support, announcements, webapp
from bot.keyboards import WEBAPP_URL
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Нет BOT_TOKEN в .env!")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# Middleware
class DBSessionMiddleware:
    async def __call__(self, handler, event, data):
        async with AsyncSessionLocal() as session:
            data["session"] = session
            return await handler(event, data)

class BanCheckMiddleware:
    async def __call__(self, handler, event, data):
        from models import User
        from sqlalchemy import select

        user_id = None
        if hasattr(event, 'from_user') and event.from_user:
            user_id = event.from_user.id
        elif hasattr(event, 'message') and event.message and event.message.from_user:
            user_id = event.message.from_user.id

        if user_id:
            session = data.get('session')
            if session:
                result = await session.execute(select(User).where(User.telegram_id == user_id))
                user = result.scalar_one_or_none()

                if user and user.is_banned:
                    if user.ban_expires and user.ban_expires < datetime.now():
                        user.is_banned = False
                        user.ban_reason = None
                        user.ban_expires = None
                        await session.commit()
                    else:
                        if hasattr(event, 'text') and str(event.text).startswith('/start'):
                            return await handler(event, data)
                        
                        ban_text = "🚫 <b>Вы забанены!</b>\n\n"
                        if user.ban_reason:
                            ban_text += f"Причина: {user.ban_reason}\n"
                        if user.ban_expires:
                            ban_text += f"Срок: до {user.ban_expires.strftime('%d.%m.%Y %H:%M')}"
                        else:
                            ban_text += "Срок: навсегда"
                        
                        if hasattr(event, 'message') and event.message:
                            await event.message.answer(ban_text, parse_mode="HTML")
                        return

        return await handler(event, data)

# Задачи планировщика
async def check_banned_users():
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
            await session.commit()
            try:
                await bot.send_message(user.telegram_id, "✅ <b>Ваш бан истёк!</b>", parse_mode="HTML")
            except:
                pass

async def check_seasons():
    from models import Season
    from sqlalchemy import select
    
    async with AsyncSessionLocal() as session:
        now = datetime.now()
        result = await session.execute(
            select(Season).where(Season.is_active == False, Season.start_date <= now)
        )
        for season in result.scalars():
            season.is_active = True
            await session.commit()
            logger.info(f"Сезон '{season.name}' начался!")

async def check_support_reminders():
    from models import SupportTicket
    from sqlalchemy import select, and_
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    
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
            ticket.reminder_count += 1
            if ticket.reminder_count >= 3:
                ticket.status = 'closed'
                ticket.closed_at = now
            await session.commit()

async def set_bot_commands():
    commands = [
        BotCommand(command="start", description="🚀 Запустить бота"),
        BotCommand(command="profile", description="👤 Профиль"),
        BotCommand(command="game", description="🎮 Mini App"),
        BotCommand(command="tasks", description="📋 Задания"),
        BotCommand(command="support", description="🆘 Поддержка"),
    ]
    await bot.set_my_commands(commands)

async def on_startup():
    logger.info("🚀 Запуск бота...")
    
    # Создание таблиц
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Таблицы БД созданы")
    
    # Миграции
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
                except:
                    pass
        
        add_col("blocks_placed", "INTEGER DEFAULT 0")
        add_col("reactions_triggered", "INTEGER DEFAULT 0")
        add_col("reactor_level", "INTEGER DEFAULT 1")
        add_col("total_energy_produced", "INTEGER DEFAULT 0")
        add_col("farm_state_json", "TEXT")
        add_col("temp", "INTEGER DEFAULT 0")
        add_col("max_temp", "INTEGER DEFAULT 100")
        add_col("level", "INTEGER DEFAULT 1")
        add_col("xp", "INTEGER DEFAULT 0")
        add_col("streak_days", "INTEGER DEFAULT 0")
        add_col("click_power", "INTEGER DEFAULT 1")
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка миграции: {e}")
    
    # Роутеры
    dp.include_router(start.router)
    dp.include_router(profile.router)
    dp.include_router(tasks.router)
    dp.include_router(support.router)
    dp.include_router(announcements.router)
    dp.include_router(webapp.router)
    
    # Middleware
    dp.message.middleware(DBSessionMiddleware())
    dp.callback_query.middleware(DBSessionMiddleware())
    dp.message.middleware(BanCheckMiddleware())
    dp.callback_query.middleware(BanCheckMiddleware())
    
    # Планировщик
    scheduler.add_job(check_banned_users, IntervalTrigger(minutes=5), id='bans')
    scheduler.add_job(check_seasons, IntervalTrigger(hours=1), id='seasons')
    scheduler.add_job(check_support_reminders, IntervalTrigger(hours=6), id='support')
    scheduler.start()
    
    # Команды
    await set_bot_commands()
    
    # Админка
    init_bot(bot)
    
    logger.info("✅ Бот запущен!")

async def on_shutdown():
    logger.info("Бот останавливается...")
    scheduler.shutdown()
    await bot.session.close()

async def main():
    await on_startup()
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        asyncio.run(on_shutdown())
