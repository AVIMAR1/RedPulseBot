#!/usr/bin/env python3
"""
Скрипт сброса и миграции БД для RedPulseBot
Использовать с осторожностью! Все данные будут удалены.
"""

import sqlite3
import os
import shutil
from datetime import datetime

DB_PATH = 'redpulse.db'
BACKUP_PATH = f'redpulse_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'

def reset_database():
    """Сбрасывает БД и создаёт новую структуру"""
    
    # Создаём бэкап
    if os.path.exists(DB_PATH):
        print(f"📦 Создаём бэкап: {BACKUP_PATH}")
        shutil.copy2(DB_PATH, BACKUP_PATH)
        print(f"✅ Бэкап создан: {BACKUP_PATH}")
    
    # Подключаемся к БД
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Включаем внешние ключи
    cursor.execute("PRAGMA foreign_keys = ON")
    
    # Получаем список всех таблиц
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    
    # Отключаем внешние ключи для удаления
    cursor.execute("PRAGMA foreign_keys = OFF")
    
    # Удаляем все таблицы
    print("🗑️  Удаляем старые таблицы...")
    for table in tables:
        table_name = table[0]
        if table_name != 'sqlite_sequence':
            cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
            print(f"   └─ Удалена: {table_name}")
    
    # Создаём новые таблицы
    print("\n📋 Создаём новую структуру БД...")
    
    # Users
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            
            -- Валюты
            click_coins INTEGER DEFAULT 0,
            stars INTEGER DEFAULT 0,
            crystals INTEGER DEFAULT 0,
            
            -- Рефералы
            referrer_id INTEGER,
            referral_bonus INTEGER DEFAULT 0,
            referrals_count INTEGER DEFAULT 0,
            
            -- Статистика
            total_clicks INTEGER DEFAULT 0,
            tasks_completed INTEGER DEFAULT 0,
            warnings_count INTEGER DEFAULT 0,
            
            -- Прогресс
            level INTEGER DEFAULT 1,
            xp INTEGER DEFAULT 0,
            
            -- Streak
            streak_days INTEGER DEFAULT 0,
            streak_last_date TEXT,
            last_daily_reward_at TEXT,
            last_random_bonus_at TEXT,
            
            -- Профиль
            gender TEXT,
            current_title_id INTEGER,
            pet_type TEXT,
            pet_name TEXT,
            pet_level INTEGER DEFAULT 1,
            pet_xp INTEGER DEFAULT 0,
            pet_hunger INTEGER DEFAULT 0,
            pet_happiness INTEGER DEFAULT 50,
            pet_last_interaction TEXT,
            
            -- Бусты
            energy_multiplier INTEGER DEFAULT 1,
            click_power INTEGER DEFAULT 1,
            auto_clicker INTEGER DEFAULT 0,
            theme TEXT,
            
            -- Ферма (реактор)
            blocks_placed INTEGER DEFAULT 0,
            reactions_triggered INTEGER DEFAULT 0,
            reactor_level INTEGER DEFAULT 1,
            total_energy_produced INTEGER DEFAULT 0,
            
            -- Бан
            is_banned INTEGER DEFAULT 0,
            ban_reason TEXT,
            ban_expires TEXT,
            banned_at TEXT,
            
            -- Временные метки
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("   └─ users ✓")
    
    # Titles
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS titles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            category TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("   └─ titles ✓")
    
    # User titles
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_titles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title_id INTEGER NOT NULL,
            obtained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source TEXT,
            UNIQUE(user_id, title_id)
        )
    """)
    print("   └─ user_titles ✓")
    
    # Achievements
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            category TEXT,
            metric TEXT NOT NULL,
            threshold INTEGER DEFAULT 0,
            reward_title_id INTEGER,
            reward_coins INTEGER DEFAULT 0,
            reward_stars INTEGER DEFAULT 0,
            reward_crystals INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("   └─ achievements ✓")
    
    # User achievements
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            achievement_id INTEGER NOT NULL,
            completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, achievement_id)
        )
    """)
    print("   └─ user_achievements ✓")
    
    # Clans
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            tag TEXT UNIQUE,
            description TEXT,
            owner_id INTEGER NOT NULL,
            treasury_coins INTEGER DEFAULT 0,
            treasury_stars INTEGER DEFAULT 0,
            treasury_crystals INTEGER DEFAULT 0,
            war_schedule_json TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("   └─ clans ✓")
    
    # Clan members
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clan_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clan_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT DEFAULT 'member',
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(clan_id, user_id)
        )
    """)
    print("   └─ clan_members ✓")
    
    # Global bank
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS global_bank (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            coins INTEGER DEFAULT 0,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            target INTEGER DEFAULT 100000,
            bonus_active_until TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO global_bank (id, coins, xp, level, target) VALUES (1, 0, 0, 1, 100000)")
    print("   └─ global_bank ✓")
    
    # Wheel config
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS wheel_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            segments_json TEXT,
            cooldown_hours INTEGER DEFAULT 24,
            is_active INTEGER DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("   └─ wheel_config ✓")
    
    # User wheel
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_wheel (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            last_spin_at TEXT,
            last_results_json TEXT
        )
    """)
    print("   └─ user_wheel ✓")
    
    # Auction lots
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auction_lots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            start_at TEXT NOT NULL,
            end_at TEXT NOT NULL,
            min_bid INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            winner_user_id INTEGER,
            winner_bid INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("   └─ auction_lots ✓")
    
    # Auction bids
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auction_bids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lot_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("   └─ auction_bids ✓")
    
    # Events
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            start_at TEXT,
            end_at TEXT,
            settings_json TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("   └─ events ✓")
    
    # Tasks
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            task_type TEXT NOT NULL,
            channel_id TEXT,
            channel_url TEXT,
            reward_coins INTEGER DEFAULT 10,
            reward_stars INTEGER DEFAULT 0,
            reward_crystals INTEGER DEFAULT 0,
            max_completions INTEGER DEFAULT -1,
            cooldown_hours INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("   └─ tasks ✓")
    
    # User tasks
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task_id INTEGER,
            completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reward_claimed INTEGER DEFAULT 1
        )
    """)
    print("   └─ user_tasks ✓")
    
    # Seasons
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS seasons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            is_active INTEGER DEFAULT 0,
            prize_1st TEXT,
            prize_2nd TEXT,
            prize_3rd TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("   └─ seasons ✓")
    
    # Season ratings
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS season_ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_id INTEGER,
            user_id INTEGER,
            stars_earned INTEGER DEFAULT 0,
            rank INTEGER
        )
    """)
    print("   └─ season_ratings ✓")
    
    # Support tickets
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            status TEXT DEFAULT 'open',
            subject TEXT,
            ticket_type TEXT DEFAULT 'question',
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reminder_count INTEGER DEFAULT 0,
            closed_at TEXT,
            closed_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("   └─ support_tickets ✓")
    
    # Support messages
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS support_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            sender_type TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("   └─ support_messages ✓")
    
    # User notices
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_notices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            notice_type TEXT DEFAULT 'message',
            status TEXT DEFAULT 'open',
            subject TEXT,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed_at TEXT,
            closed_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("   └─ user_notices ✓")
    
    # User notice messages
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_notice_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notice_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            sender_type TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("   └─ user_notice_messages ✓")
    
    # Cases
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price_coins INTEGER DEFAULT 0,
            price_crystals INTEGER DEFAULT 0,
            rewards_json TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("   └─ cases ✓")
    
    # User cases
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            case_id INTEGER NOT NULL,
            count INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("   └─ user_cases ✓")
    
    # Promo codes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS promo_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            reward_coins INTEGER DEFAULT 0,
            reward_stars INTEGER DEFAULT 0,
            reward_crystals INTEGER DEFAULT 0,
            max_uses INTEGER DEFAULT 1,
            used_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            expires_at TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("   └─ promo_codes ✓")
    
    # Promo redemptions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS promo_redemptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            promo_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("   └─ promo_redemptions ✓")
    
    # Broadcast messages
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS broadcast_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            broadcast_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL
        )
    """)
    print("   └─ broadcast_messages ✓")
    
    # Создаём индексы
    print("\n📊 Создаём индексы...")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_users_stars ON users(stars)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_users_total_clicks ON users(total_clicks)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_users_last_activity ON users(last_activity)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_users_level ON users(level)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_users_xp ON users(xp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_users_telegram_id ON users(telegram_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_support_tickets_status_last ON support_tickets(status, last_activity)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_support_messages_ticket_created ON support_messages(ticket_id, created_at)")
    print("   └─ Индексы созданы ✓")
    
    # Включаем внешние ключи обратно
    cursor.execute("PRAGMA foreign_keys = ON")
    
    # Сохраняем и закрываем
    conn.commit()
    conn.close()
    
    print("\n✅ БД успешно сброшена и создана заново!")
    print(f"📁 Бэкап старой БД: {BACKUP_PATH}")
    print("\n⚠️  НЕ ЗАБУДЬТЕ:")
    print("   1. Перезапустить бота и сервер")
    print("   2. Проверить работу всех функций")

if __name__ == "__main__":
    print("🔴 ВНИМАНИЕ! Этот скрипт удалит ВСЕ данные из БД!")
    print("   Будет создан бэкап, но все равно используйте с осторожностью!")
    response = input("\nВы уверены? Введите 'yes' для продолжения: ")
    if response.lower() == 'yes':
        reset_database()
    else:
        print("❌ Отменено")
