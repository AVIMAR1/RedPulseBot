#!/usr/bin/env python3
"""
Скрипт для локальной разработки Red Pulse Mini App
Запускает сервер и бота одновременно
"""

import subprocess
import sys
import os

def run_local():
    print("=" * 60)
    print("🚀 Red Pulse Mini App - Локальная разработка")
    print("=" * 60)
    print()
    print("📡 Сервер (FastAPI):")
    print("   └─ http://127.0.0.1:8000")
    print("   └─ Mini App: http://127.0.0.1:8000/webapp")
    print("   └─ Админка:  http://127.0.0.1:8000/")
    print()
    print("🤖 Бот запущен и ожидает команды")
    print()
    print("💡 Для тестирования Mini App в Telegram:")
    print("   1. Откройте бота")
    print("   2. Нажмите /game")
    print("   3. Telegram откроет превью по http://127.0.0.1:8000/webapp")
    print()
    print("⚠️  Внимание: Mini App будет работать только на этом ПК!")
    print("   Для доступа из Telegram нужен HTTPS (ngrok)")
    print()
    print("=" * 60)
    print()
    
    # Запускаем сервер и бота
    server_proc = subprocess.Popen(
        [sys.executable, "run_server.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding='utf-8'
    )
    
    bot_proc = subprocess.Popen(
        [sys.executable, "run_bot.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding='utf-8'
    )
    
    print("✅ Сервер и бот запущены!")
    print("   Нажмите Ctrl+C для остановки")
    print()
    
    try:
        # Выводим логи обоих процессов
        while True:
            # Логи сервера
            if server_proc.poll() is not None:
                line = server_proc.stdout.readline()
                if line:
                    print(f"[SERVER] {line.strip()}")
            
            # Логи бота
            if bot_proc.poll() is not None:
                line = bot_proc.stdout.readline()
                if line:
                    print(f"[BOT] {line.strip()}")
            
            if server_proc.poll() is None and bot_proc.poll() is None:
                # Оба процесса работают
                import time
                time.sleep(0.1)
            else:
                break
                
    except KeyboardInterrupt:
        print("\n\n⏹️  Остановка...")
        server_proc.terminate()
        bot_proc.terminate()
        server_proc.wait()
        bot_proc.wait()
        print("✅ Остановлено")

if __name__ == "__main__":
    run_local()
