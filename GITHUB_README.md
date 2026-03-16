# 🎮 Red Pulse Mini App

Telegram бот с Mini App: кликер, казино, магазин, задания и система достижений.

## 🚀 Быстрый старт

### 1. Клонирование

```bash
git clone https://github.com/ваш-username/redpulse-bot.git
cd redpulse-bot
```

### 2. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 3. Настройка

Скопируйте шаблон и заполните своими данными:

```bash
cp .env.example .env
```

Откройте `.env` и укажите:

```env
# Токен от @BotFather
BOT_TOKEN=your_bot_token

# URL вашего домена (HTTPS обязателен)
WEBAPP_URL=https://your-domain.com/webapp

# Пароль админки
ADMIN_PASSWORD=your_secure_password
```

### 4. Запуск

```bash
# Сервер (Mini App + API)
python run_server.py

# Бот (в другом терминале)
python run_bot.py
```

### 5. Настройка nginx (для продакшена)

```bash
# Установите nginx
sudo apt install nginx -y

# Создайте конфиг
sudo nano /etc/nginx/sites-available/redpulse

# Добавьте конфиг (см. nginx.conf.example)

# Активируйте
sudo ln -s /etc/nginx/sites-available/redpulse /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# Получите SSL сертификат
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your-domain.com
```

## 📁 Структура

```
redpulse-bot/
├── bot/                    # Telegram бот
│   ├── handlers/          # Обработчики команд
│   └── keyboards.py       # Клавиатуры
├── webapp/                # Mini App (frontend)
│   └── index.html        # Главный экран
├── webapp_routes.py       # API для Mini App
├── admin.py               # Админ-панель + сервер
├── main.py                # Точка входа бота
├── models.py              # Модели БД
├── database.py            # Подключение к БД
├── requirements.txt       # Зависимости
├── .env.example          # Шаблон переменных
└── README.md             # Эта инструкция
```

## 🔒 Безопасность

⚠️ **Никогда не коммитьте `.env` и `secrets.py` в git!**

Файлы `.env` и `secrets.py` добавлены в `.gitignore`.

Для продакшена используйте:
- Переменные окружения
- Менеджеры секретов (Docker secrets, Vault)
- Приватные репозитории

## 📖 Документация

- [LAUNCH.md](LAUNCH.md) — Инструкция по запуску
- [DEV_LOCAL.md](DEV_LOCAL.md) — Локальная разработка
- [START.md](START.md) — Быстрый старт

## 🛠 Технологии

- **Backend**: Python 3.9+, FastAPI, aiogram 3.x
- **Database**: SQLite + SQLAlchemy (Async)
- **Frontend**: HTML, CSS, JavaScript (Vanilla)
- **Server**: Uvicorn, nginx
- **SSL**: Let's Encrypt

## 📦 Зависимости

Основные:
- `aiogram` — Telegram бот
- `fastapi` — веб-сервер
- `sqlalchemy` — ORM
- `uvicorn` — ASGI сервер

Полный список в `requirements.txt`

## 🎮 Функционал

### Mini App
- 🖱️ Кликер с энергией и бустами
- 🎰 Казино (кости, слоты, блэкджек)
- 🛒 Магазин (кейсы, скины, аватары)
- 📋 Задания с наградами
- 👤 Профиль со статистикой
- 🏆 Рейтинг игроков

### Бот
- 🆘 Поддержка (тикеты)
- 📢 Анонсы сезонов
- 📋 Задания
- 👤 Краткий профиль

### Админ-панель
- 📊 Дашборд со статистикой
- 👥 Управление пользователями
- 💰 Выдача валюты
- 🚫 Бан/разбан
- 📢 Рассылки

## 🤝 Contributing

1. Fork репозиторий
2. Создайте ветку (`git checkout -b feature/amazing-feature`)
3. Закоммитьте изменения (`git commit -m 'Add amazing feature'`)
4. Запушьте (`git push origin feature/amazing-feature`)
5. Откройте Pull Request

## 📄 Лицензия

MIT

## 📞 Поддержка

Вопросы и предложения: создайте Issue в репозитории

---

**Создано для Red Pulse Bot** 🎮
