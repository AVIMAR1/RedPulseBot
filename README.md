# 🎮 Red Pulse Mini App

Telegram Mini App для бота Red Pulse с кликером, казино, магазином и системой достижений.

## 🔒 Безопасность

⚠️ **Этот репозиторий публичный!**

Файлы с секретами (`.env`, `secrets.py`) добавлены в `.gitignore` и **не должны** коммититься.

Перед публикацией:
1. Удалите `.env` из git (если был закоммичен)
2. Используйте `.env.example` как шаблон
3. На сервере создайте `.env` с реальными данными

## 📋 Структура проекта

```
redpulse-bot/
├── bot/                    # Бот (aiogram)
│   ├── handlers/          # Хендлеры команд
│   │   ├── start.py       # /start, Mini App кнопка
│   │   ├── profile.py     # /profile (краткий)
│   │   ├── tasks.py       # /tasks
│   │   ├── support.py     # /support (полная)
│   │   └── announcements.py # /announcements
│   └── keyboards.py       # Клавиатуры
├── webapp/                # Mini App (веб-интерфейс)
│   └── index.html         # Главный экран Mini App
├── webapp_routes.py       # API для Mini App (FastAPI)
├── admin.py               # Админ-панель + сервер
├── main.py                # Точка входа бота
└── models.py              # Модели базы данных
```

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 2. Настройка переменных окружения

Откройте файл `.env` и укажите:

```env
BOT_TOKEN=your_bot_token_from_botfather
DATABASE_URL=sqlite+aiosqlite:///./redpulse.db
WEBAPP_URL=https://your-domain.com/webapp
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your_secure_password
```

### 3. Настройка Mini App в Telegram

#### Вариант A: Локальная разработка (ngrok)

1. Установите ngrok: https://ngrok.com/download

2. Запустите сервер:
```bash
python admin.py
```

3. В другом терминале запустите ngrok:
```bash
ngrok http 8000
```

4. Скопируйте HTTPS URL из ngrok (например: `https://abc123.ngrok.io`)

5. В @BotFather:
   - `/mybots` → выберите бота
   - **Bot Settings** → **Menu Button** → **Configure Menu Button**
   - Отправьте URL: `https://abc123.ngrok.io/webapp`
   - Введите название кнопки: `🎮 Открыть игру`

#### Вариант B: Production (свой домен)

1. Разместите проект на сервере с HTTPS
2. Обновите `WEBAPP_URL` в `.env`
3. Настройте в @BotFather как выше

### 4. Запуск бота

```bash
python main.py
```

## 🎯 Функционал Mini App

### 🏠 Главная страница
- Баланс пользователя (монеты, звёзды, кристаллы)
- Навигация по разделам

### 🎮 Кликер
- Клик для заработка монет
- Энергия (1000 ед., восстанавливается)
- Бусты:
  - 🔋 Энергия +500
  - ⚡ Сила +1
  - 🤖 Автокликер
  - 💎 Обмен на кристаллы

### 🎰 Казино
- **Кости** 🎲: выпадет 4-6 = выигрыш x2
- **Слоты** 🎰: комбинации с множителями
- **21 очко** 🃏: блэкджек против дилера

### 🛒 Магазин
- **Кейсы**: случайные награды
- **Бусты**: усиления для кликера
- **Скины**: темы оформления
- **Аватары**: иконки профиля

### 📋 Задания
- Подписка на каналы
- Награды: монеты и звёзды

### 👤 Профиль
- Уровень и XP
- Статистика
- Streak (серия входов)
- Рефералы

### 🏆 Рейтинг
- Топ игроков по звёздам

## 🤖 Функционал бота

### Команды
- `/start` — Запустить бота
- `/profile` — Краткий профиль
- `/game` — Открыть Mini App
- `/tasks` — Задания
- `/support` — Поддержка
- `/announcements` — Анонсы

### Кнопки меню
- 🎮 Red Pulse Game — открыть Mini App
- 👤 Профиль — краткая информация
- 🆘 Поддержка — обращение в поддержку
- 📢 Анонсы — новости и сезоны
- 📋 Задания — список заданий

## 🔧 Админ-панель

Доступна по адресу: `http://127.0.0.1:8000`

Логин/пароль из `.env` (ADMIN_USERNAME/ADMIN_PASSWORD)

### Возможности
- 📊 Дашборд со статистикой
- 👥 Управление пользователями
- 💰 Выдача валюты
- 🚫 Бан/разбан
- 📢 Рассылки
- 📋 Задания
- 🏆 Сезоны
- 🎁 Награды
- 🆘 Поддержка

## 📡 API Mini App

### Endpoints

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/webapp` | Главная страница Mini App |
| GET | `/api/user/{user_id}` | Данные пользователя |
| POST | `/api/save-clicks` | Сохранение прогресса кликера |
| POST | `/api/buy-boost` | Покупка буста |
| POST | `/api/exchange-to-crystals` | Обмен на кристаллы |
| GET | `/api/profile/{user_id}` | Профиль |
| GET | `/api/tasks/{user_id}` | Задания |
| POST | `/api/complete-task` | Выполнение задания |
| GET | `/api/rating` | Рейтинг игроков |
| GET | `/api/shop/{category}` | Товары магазина |
| POST | `/api/buy-shop-item` | Покупка товара |
| POST | `/api/casino-dice` | Игра в кости |
| POST | `/api/casino-slots` | Слоты |
| POST | `/api/casino-bj-start` | Начать блэкджек |
| POST | `/api/casino-bj-hit` | Взять карту |
| POST | `/api/casino-bj-stand` | Хватит |

## 🎨 Темы оформления

Mini App поддерживает темы:
- 🔴 Красная (по умолчанию)
- 🔵 Синяя
- 🟡 Золотая
- 🟣 Тёмная

## 💡 Советы

1. **HTTPS обязателен**: Telegram требует HTTPS для Mini App
2. **ngrok для тестов**: используйте бесплатный тариф для разработки
3. **Production**: разверните на Vercel, Railway, или своём сервере
4. **Кэширование**: для продакшена добавьте Redis
5. **Безопасность**: проверьте валидацию `initData` от Telegram

## 🐛 Решение проблем

### Mini App не открывается
- Проверьте HTTPS URL
- Убедитесь, что сервер запущен
- Проверьте CORS настройки

### Данные не сохраняются
- Проверьте подключение к БД
- Убедитесь, что `redpulse.db` существует

### Бот не отвечает
- Проверьте BOT_TOKEN
- Убедитесь, что все зависимости установлены

## 📦 Зависимости

- `aiogram` — Telegram бот
- `fastapi` — веб-сервер
- `sqlalchemy` + `aiosqlite` — база данных
- `uvicorn` — ASGI сервер
- `apscheduler` — планировщик задач

## 📄 Лицензия

MIT

---

**Создано для Red Pulse Bot** 🎮
