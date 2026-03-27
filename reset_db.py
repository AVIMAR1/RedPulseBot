#!/usr/bin/env python3
"""
RedPulseBot - Сброс БД к чистой структуре v0.1.7
Удаляет ВСЕ данные и создаёт новую структуру
"""

import sqlite3
import shutil
from datetime import datetime

DB_PATH = 'redpulse.db'
BACKUP_PATH = f'redpulse_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'

def reset_database():
    # Бэкап
    try:
        shutil.copy2(DB_PATH, BACKUP_PATH)
        print(f"✅ Бэкап создан: {BACKUP_PATH}")
    except FileNotFoundError:
        print("ℹ️  Старой БД не было, создаём новую")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = OFF")

    # Удаляем все таблицы
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    
    for table in tables:
        if table[0] != 'sqlite_sequence':
            cursor.execute(f"DROP TABLE IF EXISTS {table[0]}")
            print(f"   └─ Удалена: {table[0]}")

    # Создаём новые таблицы
    print("\n📋 Создаём новую структуру...")

    # Users
    cursor.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            click_coins INTEGER DEFAULT 0,
            stars INTEGER DEFAULT 0,
            crystals INTEGER DEFAULT 0,
            referrer_id INTEGER,
            referrals_count INTEGER DEFAULT 0,
            total_clicks INTEGER DEFAULT 0,
            tasks_completed INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            xp INTEGER DEFAULT 0,
            streak_days INTEGER DEFAULT 0,
            streak_last_date TEXT,
            last_daily_reward_at TEXT,
            blocks_placed INTEGER DEFAULT 0,
            reactions_triggered INTEGER DEFAULT 0,
            reactor_level INTEGER DEFAULT 1,
            total_energy_produced INTEGER DEFAULT 0,
            farm_state_json TEXT,
            temp INTEGER DEFAULT 0,
            max_temp INTEGER DEFAULT 100,
            click_power INTEGER DEFAULT 1,
            energy_multiplier INTEGER DEFAULT 1,
            auto_clicker INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            ban_reason TEXT,
            ban_expires TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("   └─ users ✓")

    # Tasks
    cursor.execute("""
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            task_type TEXT NOT NULL,
            channel_url TEXT,
            reward_coins INTEGER DEFAULT 10,
            reward_stars INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("   └─ tasks ✓")

    # User tasks
    cursor.execute("""
        CREATE TABLE user_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            task_id INTEGER NOT NULL,
            completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("   └─ user_tasks ✓")

    # Seasons
    cursor.execute("""
        CREATE TABLE seasons (
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

    # Support tickets
    cursor.execute("""
        CREATE TABLE support_tickets (
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
        CREATE TABLE support_messages (
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

    # Cases
    cursor.execute("""
        CREATE TABLE cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price_coins INTEGER DEFAULT 0,
            price_crystals INTEGER DEFAULT 0,
            rewards_json TEXT,
            is_active INTEGER DEFAULT 1
        )
    """)
    print("   └─ cases ✓")

    # User cases
    cursor.execute("""
        CREATE TABLE user_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            case_id INTEGER NOT NULL,
            count INTEGER DEFAULT 1
        )
    """)
    print("   └─ user_cases ✓")

    # Global bank
    cursor.execute("""
        CREATE TABLE global_bank (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            coins INTEGER DEFAULT 0,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            target INTEGER DEFAULT 100000,
            bonus_active_until TEXT
        )
    """)
    cursor.execute("INSERT INTO global_bank (id, coins, xp, level, target) VALUES (1, 0, 0, 1, 100000)")
    print("   └─ global_bank ✓")

    # Broadcast messages
    cursor.execute("""
        CREATE TABLE broadcast_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            broadcast_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL
        )
    """)
    print("   └─ broadcast_messages ✓")

    # Индексы
    cursor.execute("CREATE INDEX ix_users_stars ON users(stars)")
    cursor.execute("CREATE INDEX ix_users_telegram_id ON users(telegram_id)")
    cursor.execute("CREATE INDEX ix_users_level ON users(level)")
    cursor.execute("CREATE INDEX ix_support_tickets_status ON support_tickets(status)")
    print("   └─ Индексы ✓")

    conn.commit()
    conn.close()

    print("\n✅ БД сброшена к v0.1.7!")
    print(f"📁 Бэкап: {BACKUP_PATH}")

if __name__ == "__main__":
    print("🔴 Сброс БД RedPulseBot v0.1.7")
    print("   Все данные будут удалены!")
    response = input("\nПродолжить? (yes): ")
    if response.lower() == 'yes':
        reset_database()
    else:
        print("❌ Отменено")
