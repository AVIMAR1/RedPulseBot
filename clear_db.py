#!/usr/bin/env python3
"""
Скрипт полной очистки БД RedPulseBot
Удаляет ВСЕ данные из таблиц (структура сохраняется)
"""

import sqlite3
import os
import shutil
from datetime import datetime

DB_PATH = 'redpulse.db'
BACKUP_PATH = f'redpulse_FULL_BACKUP_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'

def clear_database():
    """Очищает ВСЕ данные из БД"""
    
    # Создаём полный бэкап
    if os.path.exists(DB_PATH):
        print(f"📦 Создаём полную копию БД: {BACKUP_PATH}")
        shutil.copy2(DB_PATH, BACKUP_PATH)
        print(f"✅ Бэкап создан: {BACKUP_PATH}")
        print(f"   Размер: {os.path.getsize(BACKUP_PATH) / 1024 / 1024:.2f} MB")
    
    # Подключаемся к БД
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Включаем внешние ключи
    cursor.execute("PRAGMA foreign_keys = ON")
    
    # Получаем список всех таблиц
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = cursor.fetchall()
    
    print(f"\n🗑️  Очищаем данные из {len(tables)} таблиц...")
    
    # Очищаем все таблицы (в правильном порядке из-за внешних ключей)
    tables_to_clear = [
        'promo_redemptions',
        'user_notice_messages',
        'user_notices',
        'support_messages',
        'support_tickets',
        'season_ratings',
        'user_tasks',
        'user_cases',
        'user_titles',
        'user_achievements',
        'auction_bids',
        'clan_members',
        'broadcast_messages',
        'users',  # Пользователей очищаем после всех зависимостей
        'clans',
        'seasons',
        'events',
        'tasks',
        'cases',
        'promo_codes',
        'titles',
        'achievements',
        'auction_lots',
        'user_wheel',
        'wheel_config',
        'global_bank',
    ]
    
    for table in tables_to_clear:
        try:
            cursor.execute(f"DELETE FROM {table}")
            print(f"   └─ {table}: очищено")
        except Exception as e:
            print(f"   └─ {table}: ошибка - {e}")
    
    # Сбрасываем автоинкремент
    cursor.execute("DELETE FROM sqlite_sequence")
    
    # Сохраняем и закрываем
    conn.commit()
    conn.close()
    
    print("\n✅ БД полностью очищена!")
    print(f"📁 Бэкап старой БД: {BACKUP_PATH}")
    print("\n⚠️  НЕ ЗАБУДЬТЕ:")
    print("   1. Перезапустить бота и сервер")
    print("   2. Проверить работу всех функций")

if __name__ == "__main__":
    print("🔴 ВНИМАНИЕ! Этот скрипт удалит ВСЕ данные из БД!")
    print("   Будет создан бэкап, но все равно используйте с осторожностью!")
    print("\n   Таблицы будут очищены:")
    print("   • users (все пользователи)")
    print("   • support_tickets (все тикеты)")
    print("   • seasons, events, tasks")
    print("   • и все остальные данные")
    response = input("\nВы уверены? Введите 'yes' для продолжения: ")
    if response.lower() == 'yes':
        clear_database()
    else:
        print("❌ Отменено")
