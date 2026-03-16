#!/usr/bin/env python3
"""
Скрипт запуска сервера для Red Pulse Mini App
Запускает FastAPI сервер с админ-панелью и API для Mini App
"""

import uvicorn
import os

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🚀 Запуск сервера Red Pulse Mini App...")
    print("=" * 60)
    print("\n📡 Доступные адреса:")
    print("   └─ Админ-панель:  http://127.0.0.1:8000")
    print("   └─ Mini App:      http://127.0.0.1:8000/webapp")
    print("   └─ Тест режим:    http://127.0.0.1:8000/webapp/test")
    print("\n🔧 API Endpoints:")
    print("   └─ GET  /api/user/{user_id}")
    print("   └─ POST /api/save-clicks")
    print("   └─ GET  /api/tasks/{user_id}")
    print("   └─ GET  /api/shop/{category}")
    print("   └─ POST /api/casino-dice")
    print("   └─ POST /api/casino-slots")
    print("   └─ POST /api/casino-bj-start")
    print("\n💡 Для локальной разработки:")
    print("   1. Откройте http://127.0.0.1:8000/webapp/test")
    print("   2. Используйте тестового пользователя (ID: 123456789)")
    print("\n⚠️  Нажмите Ctrl+C для остановки")
    print("=" * 60 + "\n")
    
    uvicorn.run(
        "admin:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
        access_log=True
    )
