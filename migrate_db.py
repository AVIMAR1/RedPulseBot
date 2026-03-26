#!/usr/bin/env python3
"""
Скрипт миграции БД - добавляет колонку farm_state_json
"""

import sqlite3

DB_PATH = 'redpulse.db'

def migrate_database():
    """Добавляет колонку farm_state_json в таблицу users"""
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Проверяем是否存在 колонка
    cursor.execute("PRAGMA table_info(users)")
    cols = {row[1] for row in cursor.fetchall()}
    
    if 'farm_state_json' in cols:
        print("✅ Колонка farm_state_json уже существует")
    else:
        print("📋 Добавляем колонку farm_state_json...")
        cursor.execute("ALTER TABLE users ADD COLUMN farm_state_json TEXT")
        conn.commit()
        print("✅ Колонка добавлена")
    
    conn.close()
    print("\n✅ Миграция завершена!")

if __name__ == "__main__":
    migrate_database()
