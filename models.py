"""
RedPulseBot Models - Чистая версия v0.1.3
Только используемые таблицы
"""

from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Boolean, ForeignKey, Text, Index, UniqueConstraint
from sqlalchemy.sql import func
from database import Base

class User(Base):
    """Пользователи"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)

    # Валюты
    click_coins = Column(Integer, default=0)
    stars = Column(Integer, default=0)
    crystals = Column(Integer, default=0)

    # Рефералы
    referrer_id = Column(BigInteger, nullable=True)
    referrals_count = Column(Integer, default=0)

    # Статистика
    total_clicks = Column(Integer, default=0)
    tasks_completed = Column(Integer, default=0)

    # Прогресс
    level = Column(Integer, default=1)
    xp = Column(Integer, default=0)

    # Streak
    streak_days = Column(Integer, default=0)
    streak_last_date = Column(DateTime, nullable=True)
    last_daily_reward_at = Column(DateTime, nullable=True)

    # Ферма (реактор)
    blocks_placed = Column(Integer, default=0)
    reactions_triggered = Column(Integer, default=0)
    reactor_level = Column(Integer, default=1)
    total_energy_produced = Column(Integer, default=0)
    farm_state_json = Column(Text, nullable=True)  # Полное состояние фермы (JSON)
    
    # Банк фермы (виртуальный)
    bank_coins = Column(Integer, default=0)
    bank_stars = Column(Integer, default=0)
    bank_crystals = Column(Integer, default=0)
    
    # Температура ядра
    temp = Column(Integer, default=0)
    max_temp = Column(Integer, default=100)
    
    # Первый запуск
    first_play = Column(Boolean, default=True)

    # Бусты
    click_power = Column(Integer, default=1)
    energy_multiplier = Column(Integer, default=1)
    auto_clicker = Column(Boolean, default=False)

    # Бан
    is_banned = Column(Boolean, default=False)
    ban_reason = Column(String, nullable=True)
    ban_expires = Column(DateTime, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_activity = Column(DateTime(timezone=True), onupdate=func.now())


class Task(Base):
    """Задания"""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    task_type = Column(String, nullable=False)
    channel_url = Column(String, nullable=True)
    reward_coins = Column(Integer, default=10)
    reward_stars = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserTask(Base):
    """Выполненные задания"""
    __tablename__ = "user_tasks"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'))
    task_id = Column(Integer, ForeignKey('tasks.id'))
    completed_at = Column(DateTime(timezone=True), server_default=func.now())


class Season(Base):
    """Сезоны"""
    __tablename__ = "seasons"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, default=False)
    prize_1st = Column(String, nullable=True)
    prize_2nd = Column(String, nullable=True)
    prize_3rd = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SupportTicket(Base):
    """Тикеты поддержки"""
    __tablename__ = "support_tickets"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False, index=True)
    status = Column(String, default="open", nullable=False)
    subject = Column(String, nullable=True)
    ticket_type = Column(String(32), default="question", nullable=True)
    last_activity = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    reminder_count = Column(Integer, default=0)
    closed_at = Column(DateTime, nullable=True)
    closed_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SupportMessage(Base):
    """Сообщения поддержки"""
    __tablename__ = "support_messages"

    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, ForeignKey('support_tickets.id'), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
    sender_type = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Case(Base):
    """Кейсы с наградами"""
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    price_coins = Column(Integer, default=0)
    price_crystals = Column(Integer, default=0)
    rewards_json = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)


class UserCase(Base):
    """Кейсы пользователей"""
    __tablename__ = "user_cases"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    count = Column(Integer, default=1)


class GlobalBank(Base):
    """Общая казна"""
    __tablename__ = "global_bank"

    id = Column(Integer, primary_key=True)
    coins = Column(Integer, default=0)
    xp = Column(Integer, default=0)
    level = Column(Integer, default=1)
    target = Column(Integer, default=100000)
    bonus_active_until = Column(DateTime, nullable=True)


class BroadcastMessage(Base):
    """Сообщения рассылок"""
    __tablename__ = "broadcast_messages"

    id = Column(Integer, primary_key=True)
    broadcast_id = Column(String, nullable=False)
    user_id = Column(Integer, nullable=False)
    message_id = Column(Integer, nullable=False)


class Reward(Base):
    """Награды пользователей"""
    __tablename__ = "rewards"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    reward_type = Column(String, nullable=False)
    amount = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# Индексы
Index("ix_users_stars", User.stars)
Index("ix_users_telegram_id", User.telegram_id)
Index("ix_users_level", User.level)
Index("ix_users_reactor_level", User.reactor_level)
Index("ix_users_bank_coins", User.bank_coins)
Index("ix_support_tickets_status", SupportTicket.status)
