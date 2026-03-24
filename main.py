import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotMenu
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

# Планировщик для задач
scheduler = AsyncIOScheduler()

class DBSessionMiddleware:
    def __init__(self, session_maker):
        self.session_maker = session_maker
    
    async def __call__(self, handler, event, data):
        async with self.session_maker() as session:
            data["session"] = session
            return await handler(event, data)

class BanCheckMiddleware:
    """Middleware для проверки бана пользователя"""
    async def __call__(self, handler, event, data):
        from models import User
        from sqlalchemy import select
        
        # Получаем user_id из события
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
                
                # Если пользователь забанен
                if user and user.is_banned:
                    # Проверяем, не истек ли бан
                    if user.ban_expires and datetime.fromisoformat(user.ban_expires) < datetime.now():
                        user.is_banned = False
                        user.ban_reason = None
                        user.ban_expires = None
                        await session.commit()
                    else:
                        # Игнорируем все команды, кроме /start
                        if hasattr(event, 'text') and event.text and event.text.startswith('/start'):
                            return await handler(event, data)
                        
                        # Отправляем сообщение о бане
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
                        
                        return  # Прерываем обработку
        
        return await handler(event, data)

async def check_banned_users():
    """Проверка и разбан пользователей с истекшим сроком."""
    logger.debug("⏱ Запуск задачи check_banned_users")
    from models import User
    from sqlalchemy import select
    
    async with AsyncSessionLocal() as session:
        now = datetime.now()
        
        # Находим пользователей с истекшим баном
        expired = await session.execute(
            select(User).where(
                User.is_banned == True,
                User.ban_expires <= now,
                User.ban_expires.isnot(None)
            )
        )
        
        for user in expired.scalars():
            user.is_banned = False
            user.ban_reason = None
            user.ban_expires = None
            
            try:
                await bot.send_message(
                    user.telegram_id,
                    "✅ <b>Твой бан истек!</b>\n\n"
                    "Ты снова можешь пользоваться ботом.",
                    parse_mode="HTML"
                )
                logger.info(f"Пользователь {user.telegram_id} разбанен автоматически")
            except Exception as e:
                logger.error(f"Не удалось уведомить пользователя {user.telegram_id}: {e}")
        
        await session.commit()

def _parse_season_date(value):
    """Приводит дату сезона из БД (str или datetime) к datetime для сравнения."""
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


def _load_season_notifications():
    """Загружает множество ID сезонов, по которым уже отправлены уведомления."""
    try:
        with open("season_notifications.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("start", [])), set(data.get("end", []))
    except Exception:
        return set(), set()


def _save_season_notifications(sent_start: set, sent_end: set):
    """Сохраняет отправленные уведомления."""
    try:
        with open("season_notifications.json", "w", encoding="utf-8") as f:
            json.dump({"start": list(sent_start), "end": list(sent_end)}, f, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Не удалось сохранить season_notifications.json: {e}")


async def check_seasons_start_end():
    """Проверка начала и окончания сезонов. Уведомления отправляются только один раз на сезон."""
    logger.info("⏱ Запуск задачи check_seasons_start_end")
    from models import Season, User
    from sqlalchemy import select

    sent_start, sent_end = _load_season_notifications()

    async with AsyncSessionLocal() as session:
        now = datetime.now()

        # Начавшиеся сезоны — только если ещё не отправляли уведомление о старте
        all_inactive = await session.execute(
            select(Season).where(Season.is_active == False)
        )
        starting = []
        for season in all_inactive.scalars().all():
            if season.id in sent_start:
                continue
            start_dt = _parse_season_date(season.start_date)
            if start_dt is not None and start_dt <= now:
                starting.append(season)

        for season in starting:
            season.is_active = True
            sent_start.add(season.id)

            users = await session.execute(select(User).where(User.is_banned == False))

            end_str = ""
            if season.end_date is not None:
                end_dt = _parse_season_date(season.end_date)
                end_str = end_dt.strftime("%d.%m.%Y %H:%M") if end_dt else ""

            start_message = (
                f"🎉 <b>НОВЫЙ СЕЗОН НАЧАЛСЯ!</b>\n\n"
                f"🏆 <b>{season.name}</b>\n"
                f"{season.description or ''}\n\n"
                f"📅 Длится до: {end_str}\n\n"
                f"🔥 Зарабатывай звёзды и поднимайся в топ!\n"
                f"🥇 1 место: {season.prize_1st or 'Приз'}\n"
                f"🥈 2 место: {season.prize_2nd or 'Приз'}\n"
                f"🥉 3 место: {season.prize_3rd or 'Приз'}\n\n"
                f"⚡️ /game — играть\n"
                f"📋 /tasks — задания"
            )

            sent_count = 0
            for user in users.scalars():
                try:
                    await bot.send_message(user.telegram_id, start_message)
                    sent_count += 1
                    await asyncio.sleep(0.05)
                except Exception as e:
                    logger.error(f"Не удалось отправить уведомление {user.telegram_id}: {e}")

            logger.info(f"🔔 Сезон '{season.name}' начался! Уведомления отправлены {sent_count} пользователям")

        # Закончившиеся сезоны — только если ещё не отправляли уведомление о конце
        all_active = await session.execute(select(Season).where(Season.is_active == True))
        ending = []
        for season in all_active.scalars().all():
            if season.id in sent_end:
                continue
            end_dt = _parse_season_date(season.end_date)
            if end_dt is not None and end_dt <= now:
                ending.append(season)

        for season in ending:
            season.is_active = False
            sent_end.add(season.id)

            ratings = await session.execute(
                select(User).where(User.is_banned == False).order_by(User.stars.desc())
            )
            top_users = ratings.scalars().all()[:10]

            results = "🏁 <b>СЕЗОН ЗАВЕРШЁН!</b>\n\n"
            results += f"🏆 <b>{season.name}</b>\n\n"
            results += "🥇 <b>Топ-10 игроков:</b>\n"

            for i, user in enumerate(top_users, 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                name = user.first_name or f"User{user.telegram_id}"
                results += f"{medal} {name} — {user.stars} ⭐\n"

            results += "\n🎁 Призы будут выданы в ближайшее время!"

            users = await session.execute(select(User).where(User.is_banned == False))
            sent_count = 0
            for user in users.scalars():
                try:
                    await bot.send_message(user.telegram_id, results)
                    sent_count += 1
                    await asyncio.sleep(0.05)
                except Exception as e:
                    logger.error(f"Не удалось отправить итоги {user.telegram_id}: {e}")

            logger.info(f"🏆 Сезон '{season.name}' завершён! Итоги отправлены {sent_count} пользователям")

        await session.commit()

    _save_season_notifications(sent_start, sent_end)

async def process_bans():
    """Обработка банов и отправка уведомлений (данные из bans.json)."""
    logger.debug("⏱ Запуск задачи process_bans")
    try:
        with open("bans.json", "r", encoding="utf-8") as f:
            bans = json.load(f)
    except:
        return
    
    from models import User
    from sqlalchemy import select
    
    async with AsyncSessionLocal() as session:
        new_bans = []
        for ban in bans:
            if ban.get("status") != "notified":
                user = await session.execute(
                    select(User).where(User.telegram_id == ban["user_id"])
                )
                user = user.scalar_one_or_none()
                
                if user:
                    ban_text = (
                        f"🚫 <b>Вы забанены!</b>\n\n"
                        f"Причина: {ban['reason']}\n"
                    )
                    
                    if ban['expires']:
                        expires = datetime.fromisoformat(ban['expires'])
                        ban_text += f"Срок: до {expires.strftime('%d.%m.%Y %H:%M')}\n"
                    else:
                        ban_text += f"Срок: навсегда\n"
                    
                    try:
                        await bot.send_message(ban["user_id"], ban_text)
                        ban["status"] = "notified"
                    except Exception as e:
                        logger.error(f"Не удалось отправить уведомление о бане: {e}")
            
            new_bans.append(ban)
        
        with open("bans.json", "w", encoding="utf-8") as f:
            json.dump(new_bans, f, ensure_ascii=False, indent=2)

async def process_rewards():
    """Обработка выдач валюты (rewards.json)."""
    logger.debug("⏱ Запуск задачи process_rewards")
    try:
        with open("rewards.json", "r", encoding="utf-8") as f:
            rewards = json.load(f)
    except:
        return
    
    new_rewards = []
    for reward in rewards:
        if reward.get("status") != "notified":
            currency_emoji = {
                "coins": "🪙",
                "stars": "⭐",
                "crystals": "💎"
            }.get(reward["currency"], "💰")
            
            reward_text = (
                f"🎁 <b>Вы получили подарок!</b>\n\n"
                f"Валюта: {currency_emoji} {reward['amount']} {reward['currency']}\n"
                f"Причина: {reward['reason']}\n\n"
                f"💰 Проверь свой баланс в /profile"
            )
            
            try:
                await bot.send_message(reward["user_id"], reward_text)
                reward["status"] = "notified"
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление о награде: {e}")
        
        new_rewards.append(reward)
    
    with open("rewards.json", "w", encoding="utf-8") as f:
        json.dump(new_rewards, f, ensure_ascii=False, indent=2)

async def process_broadcasts():
    """Обработка рассылок (broadcasts.json)."""
    logger.debug("⏱ Запуск задачи process_broadcasts")
    try:
        with open("broadcasts.json", "r", encoding="utf-8") as f:
            broadcasts = json.load(f)
    except:
        return
    
    async with AsyncSessionLocal() as session:
        from models import User
        from sqlalchemy import select
        
        new_broadcasts = []
        for broadcast in broadcasts:
            if broadcast.get("status") == "pending":
                # Получаем пользователей
                if broadcast["recipients"] == "all":
                    users = await session.execute(
                        select(User).where(User.is_banned == False)
                    )
                else:
                    week_ago = datetime.now() - timedelta(days=7)
                    users = await session.execute(
                        select(User).where(
                            User.is_banned == False,
                            User.last_activity >= week_ago
                        )
                    )
                
                sent_count = 0
                for user in users.scalars():
                    try:
                        msg = await bot.send_message(user.telegram_id, broadcast["message"])
                        sent_count += 1
                        # сохраняем message_id для последующего удаления рассылки
                        try:
                            import sqlite3
                            conn2 = sqlite3.connect('redpulse.db')
                            conn2.execute(
                                "INSERT INTO broadcast_messages(broadcast_id,user_id,message_id) VALUES(?,?,?)",
                                (broadcast.get("id", ""), int(user.telegram_id), int(msg.message_id)),
                            )
                            conn2.commit()
                            conn2.close()
                        except Exception:
                            pass
                    except Exception as e:
                        logger.error(f"Ошибка отправки пользователю {user.telegram_id}: {e}")
                
                broadcast["status"] = "sent"
                broadcast["sent_at"] = datetime.now().isoformat()
                broadcast["sent_count"] = sent_count
                logger.info(f"📢 Рассылка отправлена {sent_count} пользователям")
            
            new_broadcasts.append(broadcast)
        
        with open("broadcasts.json", "w", encoding="utf-8") as f:
            json.dump(new_broadcasts, f, ensure_ascii=False, indent=2)


async def process_broadcast_deletes():
    """Удаление рассылок у пользователей по message_id (status=delete_pending)."""
    try:
        with open("broadcasts.json", "r", encoding="utf-8") as f:
            broadcasts = json.load(f)
    except Exception:
        return
    changed = False
    for b in broadcasts:
        if b.get("status") != "delete_pending":
            continue
        bid = b.get("id")
        if not bid:
            b["status"] = "deleted"
            changed = True
            continue
        # грузим message_id и удаляем
        try:
            import sqlite3
            conn = sqlite3.connect('redpulse.db')
            cursor = conn.cursor()
            cursor.execute("SELECT user_id, message_id FROM broadcast_messages WHERE broadcast_id = ?", (bid,))
            rows = cursor.fetchall()
            conn.close()
        except Exception:
            rows = []
        deleted = 0
        for user_id, message_id in rows:
            try:
                await bot.delete_message(int(user_id), int(message_id))
                deleted += 1
            except Exception:
                pass
        b["status"] = "deleted"
        b["deleted_at"] = datetime.now().isoformat()
        b["deleted_count"] = deleted
        changed = True
    if changed:
        with open("broadcasts.json", "w", encoding="utf-8") as f:
            json.dump(broadcasts, f, ensure_ascii=False, indent=2)

async def check_support_reminders():
    """Проверка и отправка напоминаний о незакрытых тикетах."""
    logger.debug("⏱ Запуск задачи check_support_reminders")
    try:
        from models import SupportTicket, User
        from sqlalchemy import select, and_
        
        async with AsyncSessionLocal() as session:
            now = datetime.now()
            
            # Находим тикеты, где ожидается ответ пользователя более 24 часов
            tickets = await session.execute(
                select(SupportTicket)
                .where(
                    and_(
                        SupportTicket.status == 'waiting_user',
                        SupportTicket.last_activity <= now - timedelta(hours=24),
                        SupportTicket.reminder_count < 3
                    )
                )
            )
            
            for ticket in tickets.scalars():
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
                            f"Если не ответить в течение {3 - ticket.reminder_count} дней, "
                            f"тикет будет автоматически закрыт.\n\n"
                            f"Нажми кнопку ниже, чтобы ответить:",
                            parse_mode="HTML",
                            reply_markup=builder.as_markup()
                        )
                        
                        ticket.reminder_count += 1
                        logger.info(f"Напоминание отправлено пользователю {ticket.user_id} по тикету {ticket.id}")
                        
                    except Exception as e:
                        logger.error(f"Ошибка отправки напоминания: {e}")
                
                if ticket.reminder_count >= 3:
                    ticket.status = 'closed'
                    ticket.closed_at = now
                    ticket.closed_by = 'system'
                    
                    try:
                        await bot.send_message(
                            ticket.user_id,
                            f"⚠️ <b>Тикет #{ticket.id} автоматически закрыт</b>\n\n"
                            f"Тикет был закрыт из-за отсутствия ответа в течение 3 дней.\n"
                            f"Если вопрос всё ещё актуален, создай новое обращение через /support",
                            parse_mode="HTML"
                        )
                    except:
                        pass
            
            await session.commit()
    except Exception as e:
        logger.error(f"Ошибка в check_support_reminders: {e}")


async def check_auctions_end():
    """Закрывает аукционы по времени и уведомляет победителя."""
    try:
        from models import AuctionLot
        from sqlalchemy import select, and_

        async with AsyncSessionLocal() as session:
            now = datetime.now()
            lots_res = await session.execute(
                select(AuctionLot).where(and_(AuctionLot.status == "active", AuctionLot.end_at <= now))
            )
            lots = lots_res.scalars().all()
            if not lots:
                return
            for lot in lots:
                lot.status = "closed"
                await session.commit()
                if lot.winner_user_id and (lot.winner_bid or 0) > 0:
                    try:
                        await bot.send_message(
                            int(lot.winner_user_id),
                            "🏁 <b>Аукцион завершён!</b>\n\n"
                            f"🎁 Лот: <b>{lot.name}</b>\n"
                            f"✅ Ты победил со ставкой <b>{lot.winner_bid}</b> 🪙\n\n"
                            "Приз будет выдан админом/системой (настройка в разработке).",
                            parse_mode="HTML",
                        )
                    except Exception as e:
                        logger.error(f"Не удалось уведомить победителя {lot.winner_user_id}: {e}")
    except Exception as e:
        logger.error(f"Ошибка в check_auctions_end: {e}")

async def set_bot_commands():
    """Установка команд бота (упрощённые для Mini App)"""
    commands = [
        BotCommand(command="start", description="🚀 Запустить бота"),
        BotCommand(command="profile", description="👤 Мой профиль"),
        BotCommand(command="game", description="🎮 Открыть Mini App"),
        BotCommand(command="tasks", description="📋 Задания"),
        BotCommand(command="support", description="🆘 Поддержка"),
        BotCommand(command="announcements", description="📢 Анонсы"),
        BotCommand(command="refresh", description="🔄 Обновить меню"),
    ]
    await bot.set_my_commands(commands)

async def main():
    # Создаем таблицы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Миграция: колонка theme в users (для кликера)
    try:
        import sqlite3
        conn = sqlite3.connect('redpulse.db')
        conn.execute("ALTER TABLE users ADD COLUMN theme VARCHAR(32)")
        conn.commit()
        conn.close()
    except Exception:
        pass

    # Миграции: новые колонки users (уровни/XP/streak/титулы/питомец/пол)
    try:
        import sqlite3
        conn = sqlite3.connect("redpulse.db")
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(users)")
        cols = {row[1] for row in cur.fetchall()}  # row[1] = name

        def add_col(name: str, ddl: str):
            if name in cols:
                return
            try:
                cur.execute(f"ALTER TABLE users ADD COLUMN {ddl}")
                cols.add(name)
            except Exception:
                pass

        add_col("level", "level INTEGER DEFAULT 1")
        add_col("xp", "xp INTEGER DEFAULT 0")
        add_col("streak_days", "streak_days INTEGER DEFAULT 0")
        add_col("streak_last_date", "streak_last_date TEXT NULL")
        add_col("last_daily_reward_at", "last_daily_reward_at TEXT NULL")
        add_col("last_random_bonus_at", "last_random_bonus_at TEXT NULL")
        add_col("current_title_id", "current_title_id INTEGER NULL")
        add_col("gender", "gender TEXT NULL")
        add_col("pet_type", "pet_type TEXT NULL")
        add_col("pet_name", "pet_name TEXT NULL")
        add_col("pet_level", "pet_level INTEGER DEFAULT 1")
        add_col("pet_xp", "pet_xp INTEGER DEFAULT 0")
        add_col("pet_hunger", "pet_hunger INTEGER DEFAULT 0")
        add_col("pet_happiness", "pet_happiness INTEGER DEFAULT 50")
        add_col("pet_last_interaction", "pet_last_interaction TEXT NULL")
        add_col("warnings_count", "warnings_count INTEGER DEFAULT 0")

        conn.commit()
        conn.close()
    except Exception:
        pass

    # Миграция: support_tickets.ticket_type
    try:
        import sqlite3
        conn = sqlite3.connect("redpulse.db")
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(support_tickets)")
        cols = {row[1] for row in cur.fetchall()}
        if "ticket_type" not in cols:
            cur.execute("ALTER TABLE support_tickets ADD COLUMN ticket_type TEXT DEFAULT 'question'")
        conn.commit()
        conn.close()
    except Exception:
        pass
    # Миграция: промокоды (на случай, если БД уже была создана раньше)
    try:
        import sqlite3
        conn = sqlite3.connect('redpulse.db')
        conn.execute(
            """CREATE TABLE IF NOT EXISTS promo_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                reward_coins INTEGER DEFAULT 0,
                reward_stars INTEGER DEFAULT 0,
                reward_crystals INTEGER DEFAULT 0,
                max_uses INTEGER DEFAULT 1,
                used_count INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                expires_at TEXT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS promo_redemptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                promo_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                redeemed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(promo_id, user_id)
            )"""
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
    # Миграция: хранение message_id для удаления рассылок
    try:
        import sqlite3
        conn = sqlite3.connect('redpulse.db')
        conn.execute(
            """CREATE TABLE IF NOT EXISTS broadcast_messages (
                broadcast_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
    # Дефолтный кейс для рефералов (если ещё нет)
    from models import Case
    from sqlalchemy import select
    async with AsyncSessionLocal() as session:
        existing = await session.execute(select(Case.name))
        names = {row[0] for row in existing.all()}
        def _add_case(name: str, desc: str, price_coins: int, price_crystals: int, rewards_json: str):
            if name in names:
                return
            session.add(Case(
                name=name,
                description=desc,
                price_coins=price_coins,
                price_crystals=price_crystals,
                rewards_json=rewards_json,
            ))
        _add_case(
            "Реферальный кейс",
            "Специальный кейс за приглашение (и новичку тоже).",
            0, 0,
            '[{"type":"stars","min":25,"max":80},{"type":"coins","min":800,"max":2500},{"type":"crystals","min":1,"max":3}]',
        )
        _add_case(
            "Эконом-кейс",
            "Побольше монет и немного звёзд.",
            1500, 0,
            '[{"type":"coins","min":2500,"max":6000},{"type":"stars","min":15,"max":40}]',
        )
        _add_case(
            "Кейс кастомизации",
            "Шанс получить тему для кликера.",
            0, 25,
            '[{"type":"theme","min":1,"max":1,"value":"gold"},{"type":"theme","min":1,"max":1,"value":"dark"},{"type":"crystals","min":2,"max":5}]',
        )
        _add_case(
            "Кейс бустеров",
            "Прокачка кликера: энергия/сила/автокликер.",
            2500, 0,
            '[{"type":"boost_power","min":1,"max":1},{"type":"boost_energy","min":1,"max":1},{"type":"boost_auto","min":1,"max":1}]',
        )
        await session.commit()

    # Дефолтные титулы и ачивки
    try:
        from models import Title, Achievement, Event
        from sqlalchemy import select
        async with AsyncSessionLocal() as session:
            t_res = await session.execute(select(Title.code))
            existing_titles = {row[0] for row in t_res.all()}

            def add_title(code: str, name: str, desc: str, category: str):
                if code in existing_titles:
                    return
                session.add(Title(code=code, name=name, description=desc, category=category, is_active=True))
                existing_titles.add(code)

            add_title("CLICKER_1K", "Кликер • 1 000", "Сделал 1 000 кликов", "clicks")
            add_title("CLICKER_10K", "Кликер • 10 000", "Сделал 10 000 кликов", "clicks")
            add_title("STREAK_7", "Streak • 7 дней", "Заходил 7 дней подряд", "streak")
            add_title("STREAK_30", "Streak • 30 дней", "Заходил 30 дней подряд", "streak")

            await session.flush()

            # Сопоставим title_id по коду
            t_map_res = await session.execute(select(Title.id, Title.code))
            t_map = {code: tid for tid, code in t_map_res.all()}

            a_res = await session.execute(select(Achievement.code))
            existing_achs = {row[0] for row in a_res.all()}

            def add_ach(code: str, name: str, desc: str, metric: str, threshold: int, reward_title_code: str | None):
                if code in existing_achs:
                    return
                session.add(
                    Achievement(
                        code=code,
                        name=name,
                        description=desc,
                        category=metric,
                        metric=metric,
                        threshold=threshold,
                        reward_title_id=t_map.get(reward_title_code) if reward_title_code else None,
                        reward_coins=0,
                        reward_stars=0,
                        reward_crystals=0,
                        is_active=True,
                    )
                )
                existing_achs.add(code)

            add_ach("ACH_CLICKS_1K", "1 000 кликов", "Достигни 1 000 кликов в кликере", "total_clicks", 1000, "CLICKER_1K")
            add_ach("ACH_CLICKS_10K", "10 000 кликов", "Достигни 10 000 кликов в кликере", "total_clicks", 10000, "CLICKER_10K")
            add_ach("ACH_STREAK_7", "Streak 7", "Заходи в бота 7 дней подряд", "streak_days", 7, "STREAK_7")
            add_ach("ACH_STREAK_30", "Streak 30", "Заходи в бота 30 дней подряд", "streak_days", 30, "STREAK_30")

            await session.commit()
    except Exception as e:
        logger.error(f"Seed титулов/ачивок не выполнен: {e}")

    # Дефолтные ивенты (выключены по умолчанию, включаются в админке)
    try:
        from models import Event
        from sqlalchemy import select
        async with AsyncSessionLocal() as session:
            e_res = await session.execute(select(Event.code))
            existing = {row[0] for row in e_res.all()}
            def add_event(code: str, name: str, desc: str, settings_json: str):
                if code in existing:
                    return
                session.add(Event(code=code, name=name, description=desc, settings_json=settings_json, is_active=False))
                existing.add(code)
            add_event(
                "NEW_YEAR",
                "Новый год",
                "Пример ивента: множители ежедневной награды.",
                '{"daily_coins_mult": 1.5, "daily_xp_mult": 1.5}',
            )
            add_event(
                "MARCH_8",
                "8 марта",
                "Пример ивента: удвоенный XP для девушек (gender=female).",
                '{"female_xp_mult": 2.0}',
            )
            await session.commit()
    except Exception as e:
        logger.error(f"Seed ивентов не выполнен: {e}")

    # Регистрируем хендлеры (только основные для бота + Mini App)
    from aiogram.types import BotMenu, WebAppInfo
    dp.include_router(start.router)        # /start, /game, Mini App кнопка
    dp.include_router(profile.router)      # /profile
    dp.include_router(tasks.router)        # /tasks
    dp.include_router(support.router)      # /support
    dp.include_router(announcements.router) # /announcements
    dp.include_router(webapp.router)       # /game через Mini App

    # Добавляем middleware
    dp.message.middleware(DBSessionMiddleware(AsyncSessionLocal))
    dp.callback_query.middleware(DBSessionMiddleware(AsyncSessionLocal))
    dp.message.middleware(BanCheckMiddleware())
    dp.callback_query.middleware(BanCheckMiddleware())

    # Устанавливаем команды бота с Menu Button для Mini App
    await set_bot_commands()
    
    # Устанавливаем Menu Button для открытия Mini App
    try:
        await bot.set_chat_menu_button(
            menu_button=BotMenu(
                text="🎮 Открыть игру",
                web_app=WebAppInfo(url=WEBAPP_URL)
            )
        )
        logger.info("✅ Menu Button настроен для Mini App")
    except Exception as e:
        logger.error(f"Ошибка настройки Menu Button: {e}")
    
    # Инициализируем админку с ботом
    init_bot(bot)
    start_admin()
    logger.info("🌐 Админка доступна по адресу http://127.0.0.1:8000")
    
    # Запускаем планировщик
    scheduler.add_job(check_seasons_start_end, IntervalTrigger(minutes=1))
    scheduler.add_job(process_broadcasts, IntervalTrigger(minutes=2))
    scheduler.add_job(process_broadcast_deletes, IntervalTrigger(minutes=1))
    scheduler.add_job(process_bans, IntervalTrigger(minutes=1))
    scheduler.add_job(process_rewards, IntervalTrigger(minutes=1))
    scheduler.add_job(check_banned_users, IntervalTrigger(minutes=5))
    scheduler.add_job(check_support_reminders, IntervalTrigger(hours=6))
    scheduler.add_job(check_auctions_end, IntervalTrigger(minutes=1))
    scheduler.start()
    
    logger.info("✅ Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())