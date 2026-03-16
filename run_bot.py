#!/usr/bin/env python3
"""
Скрипт запуска Telegram бота Red Pulse
"""

import asyncio
import os

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🤖 Запуск Telegram бота Red Pulse...")
    print("=" * 60)
    print("\n📡 Команды бота:")
    print("   └─ /start        - Запустить бота")
    print("   └─ /profile      - Профиль пользователя")
    print("   └─ /game         - Открыть Mini App")
    print("   └─ /tasks        - Задания")
    print("   └─ /support      - Поддержка")
    print("   └─ /announcements - Анонсы")
    print("\n🎮 Кнопка меню: 🎮 Red Pulse Game")
    print("\n💡 Mini App URL: http://127.0.0.1:8000/webapp")
    print("   (для работы в Telegram нужен HTTPS)")
    print("\n⚠️  Нажмите Ctrl+C для остановки")
    print("=" * 60 + "\n")
    
    from main import main
    asyncio.run(main())
