@echo off
echo ============================================================
echo Red Pulse Mini App - Локальный запуск
echo ============================================================
echo.
echo Запуск сервера (FastAPI)...
echo Сервер доступен: http://127.0.0.1:8000
echo Mini App: http://127.0.0.1:8000/webapp
echo Админка: http://127.0.0.1:8000/
echo.
echo Нажмите Ctrl+C для остановки
echo ============================================================
echo.

start "Red Pulse Server" cmd /k "python run_server.py"
timeout /t 3 /nobreak >nul

start "Red Pulse Bot" cmd /k "python run_bot.py"

echo.
echo ✅ Сервер и бот запущены в отдельных окнах!
echo.
echo Для тестирования Mini App:
echo   1. Откройте браузер: http://127.0.0.1:8000/webapp
echo   2. Или в Telegram: /game
echo.
echo Для остановки закройте окна терминала
pause
