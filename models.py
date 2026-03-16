from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Boolean, ForeignKey, Text, Index, UniqueConstraint
from sqlalchemy.sql import func
from database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    
    # Валюты
    click_coins = Column(Integer, default=0)
    stars = Column(Integer, default=0)
    crystals = Column(Integer, default=0)
    
    # Реферальная система
    referrer_id = Column(BigInteger, nullable=True)
    referral_bonus = Column(Integer, default=0)
    referrals_count = Column(Integer, default=0)
    
    # Статистика
    total_clicks = Column(Integer, default=0)
    tasks_completed = Column(Integer, default=0)
    warnings_count = Column(Integer, default=0)

    # Прогресс (уровни/опыт)
    level = Column(Integer, default=1)
    xp = Column(Integer, default=0)

    # Streak (полоса успеха) и ежедневная награда
    streak_days = Column(Integer, default=0)
    streak_last_date = Column(DateTime, nullable=True)          # дата последнего дня streak
    last_daily_reward_at = Column(DateTime, nullable=True)      # чтобы не выдавать награду дважды в сутки
    last_random_bonus_at = Column(DateTime, nullable=True)      # рандомные бонусы "как покемон в траве"

    # Профиль/кастомизация
    gender = Column(String(16), nullable=True)                  # optional: 'male' | 'female' | 'unknown'
    current_title_id = Column(Integer, ForeignKey("titles.id"), nullable=True)
    pet_type = Column(String(32), nullable=True)
    pet_name = Column(String(64), nullable=True)
    pet_level = Column(Integer, default=1)
    pet_xp = Column(Integer, default=0)
    pet_hunger = Column(Integer, default=0)                     # 0..100
    pet_happiness = Column(Integer, default=50)                 # 0..100
    pet_last_interaction = Column(DateTime, nullable=True)
    
    # Бусты
    energy_multiplier = Column(Integer, default=1)
    click_power = Column(Integer, default=1)
    auto_clicker = Column(Boolean, default=False)
    # Тема кликера: default, red, blue, gold, dark
    theme = Column(String(32), nullable=True)
    
    # Статус бана
    is_banned = Column(Boolean, default=False)
    ban_reason = Column(String, nullable=True)
    ban_expires = Column(DateTime, nullable=True)
    banned_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_activity = Column(DateTime(timezone=True), onupdate=func.now())


class Title(Base):
    __tablename__ = "titles"

    id = Column(Integer, primary_key=True)
    code = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(64), nullable=True)  # например: clicks, streak, event, clan, admin
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserTitle(Base):
    __tablename__ = "user_titles"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    title_id = Column(Integer, ForeignKey("titles.id"), nullable=False, index=True)
    obtained_at = Column(DateTime(timezone=True), server_default=func.now())
    source = Column(String(32), nullable=True)  # admin | achievement | event | clan | other

    __table_args__ = (
        UniqueConstraint("user_id", "title_id", name="uq_user_titles_user_title"),
    )


class Achievement(Base):
    __tablename__ = "achievements"

    id = Column(Integer, primary_key=True)
    code = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(64), nullable=True)          # clicks, streak, stars, casino ...
    metric = Column(String(64), nullable=False)           # total_clicks | streak_days | stars | ...
    threshold = Column(Integer, default=0)                # порог
    reward_title_id = Column(Integer, ForeignKey("titles.id"), nullable=True)
    reward_coins = Column(Integer, default=0)
    reward_stars = Column(Integer, default=0)
    reward_crystals = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserAchievement(Base):
    __tablename__ = "user_achievements"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    achievement_id = Column(Integer, ForeignKey("achievements.id"), nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "achievement_id", name="uq_user_achievements_user_achievement"),
    )


# ========== Кланы и общая казна ==========
class Clan(Base):
    __tablename__ = "clans"

    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True, nullable=False, index=True)
    tag = Column(String(16), unique=True, nullable=True, index=True)
    description = Column(Text, nullable=True)
    owner_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)

    treasury_coins = Column(Integer, default=0)
    treasury_stars = Column(Integer, default=0)
    treasury_crystals = Column(Integer, default=0)

    war_schedule_json = Column(Text, nullable=True)  # настройки войн/ивентов клана (JSON)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ClanMember(Base):
    __tablename__ = "clan_members"

    id = Column(Integer, primary_key=True)
    clan_id = Column(Integer, ForeignKey("clans.id"), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    role = Column(String(16), default="member")  # leader | officer | member
    joined_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("clan_id", "user_id", name="uq_clan_members_clan_user"),
    )


class GlobalBank(Base):
    __tablename__ = "global_bank"

    id = Column(Integer, primary_key=True)
    coins = Column(Integer, default=0)
    xp = Column(Integer, default=0)
    level = Column(Integer, default=1)
    target = Column(Integer, default=100_000)  # цель для следующего "общего бонуса"
    bonus_active_until = Column(DateTime, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ========== Колесо фортуны ==========
class WheelConfig(Base):
    __tablename__ = "wheel_config"

    id = Column(Integer, primary_key=True)
    segments_json = Column(Text, nullable=True)  # JSON массива сегментов с весами/наградами
    cooldown_hours = Column(Integer, default=24)
    is_active = Column(Boolean, default=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UserWheel(Base):
    __tablename__ = "user_wheel"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), unique=True, nullable=False, index=True)
    last_spin_at = Column(DateTime, nullable=True)
    last_results_json = Column(Text, nullable=True)  # последние 2-3 сектора для "джекпота"


# ========== Аукцион ==========
class AuctionLot(Base):
    __tablename__ = "auction_lots"

    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    start_at = Column(DateTime, nullable=False)
    end_at = Column(DateTime, nullable=False)
    min_bid = Column(Integer, default=0)
    status = Column(String(16), default="active")  # active | closed
    winner_user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=True)
    winner_bid = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AuctionBid(Base):
    __tablename__ = "auction_bids"

    id = Column(Integer, primary_key=True)
    lot_id = Column(Integer, ForeignKey("auction_lots.id"), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    amount = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ========== События (ивенты) ==========
class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    code = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    start_at = Column(DateTime, nullable=True)
    end_at = Column(DateTime, nullable=True)
    settings_json = Column(Text, nullable=True)  # JSON настроек (множители и т.п.)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    
    task_type = Column(String, nullable=False)
    
    channel_id = Column(String, nullable=True)
    channel_url = Column(String, nullable=True)
    
    reward_coins = Column(Integer, default=10)
    reward_stars = Column(Integer, default=0)
    reward_crystals = Column(Integer, default=0)
    
    max_completions = Column(Integer, default=-1)
    cooldown_hours = Column(Integer, default=0)
    
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserTask(Base):
    __tablename__ = "user_tasks"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'))
    task_id = Column(Integer, ForeignKey('tasks.id'))
    completed_at = Column(DateTime(timezone=True), server_default=func.now())
    reward_claimed = Column(Boolean, default=True)


class Season(Base):
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


class SeasonRating(Base):
    __tablename__ = "season_ratings"
    
    id = Column(Integer, primary_key=True)
    season_id = Column(Integer, ForeignKey('seasons.id'))
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'))
    stars_earned = Column(Integer, default=0)
    rank = Column(Integer, nullable=True)


# ========== НОВЫЕ ТАБЛИЦЫ ДЛЯ ПОДДЕРЖКИ ==========

class SupportTicket(Base):
    __tablename__ = "support_tickets"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False, index=True)
    
    # Статусы: open, in_progress, waiting_user, waiting_admin, closed
    status = Column(String, default="open", nullable=False)
    
    # Тема обращения (первые 100 символов сообщения)
    subject = Column(String, nullable=True)

    # Тип тикета: complaint | bug | question | other
    ticket_type = Column(String(32), default="question", nullable=True)
    
    # Время последней активности
    last_activity = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Количество уведомлений
    reminder_count = Column(Integer, default=0)
    
    # Время закрытия (если закрыт)
    closed_at = Column(DateTime, nullable=True)
    closed_by = Column(String, nullable=True)  # 'user' или 'admin'
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SupportMessage(Base):
    __tablename__ = "support_messages"
    
    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, ForeignKey('support_tickets.id'), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
    
    # Тип отправителя: 'user' или 'admin'
    sender_type = Column(String, nullable=False)
    
    # Текст сообщения
    message = Column(Text, nullable=False)
    
    # Статус прочтения (для админа)
    is_read = Column(Boolean, default=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ========== ЭКСТРЕННЫЕ СООБЩЕНИЯ/ПРЕДУПРЕЖДЕНИЯ (как чат) ==========
class UserNotice(Base):
    __tablename__ = "user_notices"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)

    # warning | message
    notice_type = Column(String(16), default="message", nullable=False)
    # open | waiting_user | waiting_admin | closed
    status = Column(String(16), default="open", nullable=False)

    subject = Column(String(128), nullable=True)
    last_activity = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    closed_at = Column(DateTime, nullable=True)
    closed_by = Column(String(16), nullable=True)  # admin
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserNoticeMessage(Base):
    __tablename__ = "user_notice_messages"

    id = Column(Integer, primary_key=True)
    notice_id = Column(Integer, ForeignKey("user_notices.id"), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)

    sender_type = Column(String(16), nullable=False)  # user | admin
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# Кейсы (награды за рефералов, покупка в магазине)
class Case(Base):
    __tablename__ = "cases"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    price_coins = Column(Integer, default=0)
    price_crystals = Column(Integer, default=0)
    # Награды: JSON список {"type": "coins"|"stars"|"crystals", "min": N, "max": M}
    rewards_json = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserCase(Base):
    __tablename__ = "user_cases"
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    count = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PromoCode(Base):
    __tablename__ = "promo_codes"
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False, index=True)
    reward_coins = Column(Integer, default=0)
    reward_stars = Column(Integer, default=0)
    reward_crystals = Column(Integer, default=0)
    max_uses = Column(Integer, default=1)  # 0 = unlimited
    used_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PromoRedemption(Base):
    __tablename__ = "promo_redemptions"
    id = Column(Integer, primary_key=True)
    promo_id = Column(Integer, ForeignKey("promo_codes.id"), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    redeemed_at = Column(DateTime(timezone=True), server_default=func.now())


# Кастомизация кликера (тема и т.д.)
# В User можно добавить: theme = Column(String, nullable=True) или оставить в JSON в кликере по userId
# Пока кейсы и рефералы — при открытии кейса награда пишется в User

# Индексы для производительности
Index("ix_users_stars", User.stars)
Index("ix_users_total_clicks", User.total_clicks)
Index("ix_users_last_activity", User.last_activity)
Index("ix_users_level", User.level)
Index("ix_users_xp", User.xp)
Index("ix_users_warnings_count", User.warnings_count)
Index("ix_support_tickets_status_last", SupportTicket.status, SupportTicket.last_activity)
Index("ix_support_messages_ticket_created", SupportMessage.ticket_id, SupportMessage.created_at)