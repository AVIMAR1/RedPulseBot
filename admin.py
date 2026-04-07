from fastapi import FastAPI, Request, Depends, HTTPException, Form, Query
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import sqlite3
import uvicorn
import secrets
import json
import asyncio
import uuid
from collections import deque
import threading
from threading import Thread
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
from webapp_routes import router as webapp_router

try:
    import redis  # type: ignore
except ImportError:
    redis = None

load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory="templates")
security = HTTPBasic()

# Подключаем роутер для WebApp
app.include_router(webapp_router)

# Глобальные переменные
bot = None
bot_loop = None
message_queue = deque()
queue_lock = threading.Lock()
REDIS_URL = os.getenv("REDIS_URL")
_redis_client = None

# Простейший in-memory rate limit: {key: [timestamps]}
RATE_LIMITS = {}

# Защита
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "redpulse2026")


def verify_auth(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (correct_username and correct_password):
        # Базовая защита админки: требуем корректные логин/пароль
        raise HTTPException(status_code=401, detail="Unauthorized")
    return credentials.username


def get_redis_client():
    """
    Ленивая инициализация Redis-клиента.
    Если Redis не настроен или библиотека не установлена – возвращаем None.
    """
    global _redis_client
    if not (redis and REDIS_URL):
        return None
    if _redis_client is None:
        try:
            _redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        except Exception:
            _redis_client = None
    return _redis_client


def rate_limit(key_prefix: str, limit: int, per_seconds: int, request: Request):
    """
    Простейший rate limiting по IP в памяти процесса.
    Не идеален, но защищает от грубого спама форм/апи.
    """
    ip = request.client.host if request.client else "unknown"
    key = f"{key_prefix}:{ip}"
    now = datetime.now().timestamp()
    window_start = now - per_seconds

    timestamps = RATE_LIMITS.get(key, [])
    timestamps = [t for t in timestamps if t > window_start]

    if len(timestamps) >= limit:
        raise HTTPException(
            status_code=429,
            detail="Слишком много запросов, попробуйте позже",
        )

    timestamps.append(now)
    RATE_LIMITS[key] = timestamps


def support_send_rate_limit(request: Request):
    # Ограничиваем API поддержки: не более 20 сообщений в минуту с одного IP
    rate_limit("support_send", limit=20, per_seconds=60, request=request)


def broadcast_rate_limit(request: Request):
    # Рассылка более чувствительна – максимум 5 запусков в минуту
    rate_limit("broadcast_send", limit=5, per_seconds=60, request=request)


def give_currency_rate_limit(request: Request):
    # Выдача валюты: до 30 операций в минуту
    rate_limit("give_currency", limit=30, per_seconds=60, request=request)

# Вспомогательная функция для получения статистики поддержки
def get_support_stats():
    conn = sqlite3.connect('redpulse.db')
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE status IN ('open', 'in_progress', 'waiting_admin')")
        open_support_tickets = cursor.fetchone()[0] or 0
    except:
        open_support_tickets = 0
    conn.close()
    return open_support_tickets

# Функция для добавления в очередь
def add_to_queue(user_id: int, text: str, parse_mode: str = "Markdown", reply_markup=None):
    """Добавить сообщение в очередь на отправку"""
    with queue_lock:
        message_queue.append({
            'user_id': user_id,
            'text': text,
            'parse_mode': parse_mode,
            'reply_markup': reply_markup
        })
    print(f"📨 Сообщение добавлено в очередь для пользователя {user_id}")

# Функция для отправки сообщения (вызывается в цикле бота)
async def _send_message(msg_data):
    """Внутренняя функция отправки"""
    global bot
    try:
        await bot.send_message(
            msg_data['user_id'],
            msg_data['text'],
            parse_mode=msg_data.get('parse_mode', 'Markdown'),
            reply_markup=msg_data.get('reply_markup')
        )
        print(f"✅ Сообщение успешно отправлено пользователю {msg_data['user_id']}")
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")
        return False

# Функция для обработки очереди в цикле бота
async def _process_queue():
    """Обработка очереди в цикле бота"""
    print("🔄 Обработчик очереди запущен в цикле бота")
    message_count = 0
    
    while True:
        try:
            if message_queue:
                with queue_lock:
                    msg_data = message_queue.popleft()
                
                if msg_data and bot:
                    message_count += 1
                    print(f"📤 Попытка отправки #{message_count} пользователю {msg_data['user_id']}...")
                    
                    success = await _send_message(msg_data)
                    if not success:
                        with queue_lock:
                            message_queue.appendleft(msg_data)
                        await asyncio.sleep(1)
            
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"❌ Ошибка в очереди: {e}")
            await asyncio.sleep(1)

def _get_dashboard_stats(cursor) -> dict:
    """Собирает статистику дашборда для API и шаблона."""
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
    banned_users = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 0")
    active_users = cursor.fetchone()[0] or 0
    cursor.execute("SELECT SUM(click_coins) FROM users")
    total_coins = cursor.fetchone()[0] or 0
    cursor.execute("SELECT SUM(stars) FROM users")
    total_stars = cursor.fetchone()[0] or 0
    cursor.execute("SELECT SUM(crystals) FROM users")
    total_crystals = cursor.fetchone()[0] or 0
    cursor.execute("SELECT SUM(total_clicks) FROM users")
    total_clicks = cursor.fetchone()[0] or 0
    cursor.execute("SELECT SUM(tasks_completed) FROM users")
    total_tasks = cursor.fetchone()[0] or 0
    cursor.execute("SELECT SUM(referrals_count) FROM users")
    total_referrals = cursor.fetchone()[0] or 0
    cursor.execute("SELECT SUM(referral_bonus) FROM users")
    total_referral_bonus = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE is_active = 1")
    active_tasks = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM seasons WHERE is_active = 1")
    active_seasons = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at) = DATE('now')")
    new_users_today = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM user_tasks WHERE DATE(completed_at) = DATE('now')")
    tasks_completed_today = cursor.fetchone()[0] or 0
    cursor.execute("SELECT SUM(total_clicks) FROM users WHERE DATE(last_activity) = DATE('now')")
    clicks_today = cursor.fetchone()[0] or 0
    try:
        cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE status IN ('open', 'in_progress', 'waiting_admin')")
        open_support_tickets = cursor.fetchone()[0] or 0
    except Exception:
        open_support_tickets = 0
    try:
        cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE status = 'closed'")
        closed_support_tickets = cursor.fetchone()[0] or 0
    except Exception:
        closed_support_tickets = 0
    try:
        cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE DATE(created_at) = DATE('now')")
        new_tickets_today = cursor.fetchone()[0] or 0
    except Exception:
        new_tickets_today = 0
    return {
        "total_users": total_users,
        "active_users": active_users,
        "banned_users": banned_users,
        "total_coins": total_coins,
        "total_stars": total_stars,
        "total_crystals": total_crystals,
        "total_clicks": total_clicks,
        "total_tasks": total_tasks,
        "total_referrals": total_referrals,
        "total_referral_bonus": total_referral_bonus,
        "active_tasks": active_tasks,
        "active_seasons": active_seasons,
        "new_users_today": new_users_today,
        "tasks_completed_today": tasks_completed_today,
        "clicks_today": clicks_today or 0,
        "open_support_tickets": open_support_tickets,
        "closed_support_tickets": closed_support_tickets,
        "new_tickets_today": new_tickets_today,
    }


@app.get("/api/dashboard-stats", response_class=JSONResponse)
async def api_dashboard_stats(request: Request, auth: str = Depends(verify_auth)):
    """JSON-статистика дашборда для автообновления без перезагрузки страницы."""
    conn = sqlite3.connect('redpulse.db')
    cursor = conn.cursor()
    try:
        stats = _get_dashboard_stats(cursor)
        # Форматирование чисел для отображения
        for key in ("total_coins", "total_stars", "total_crystals", "total_clicks", "total_tasks", "total_referral_bonus"):
            if key in stats and isinstance(stats[key], (int, float)):
                stats[key + "_fmt"] = f"{stats[key]:,}".replace(",", " ")
        return stats
    finally:
        conn.close()


# Главная страница админки
@app.get("/", response_class=HTMLResponse)
async def admin_panel(request: Request, auth: str = Depends(verify_auth)):
    conn = sqlite3.connect('redpulse.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Сегодняшняя дата
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Общая статистика
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
    banned_users = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 0")
    active_users = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT SUM(click_coins) FROM users")
    total_coins = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT SUM(stars) FROM users")
    total_stars = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT SUM(crystals) FROM users")
    total_crystals = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT SUM(total_clicks) FROM users")
    total_clicks = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT SUM(tasks_completed) FROM users")
    total_tasks = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT SUM(referrals_count) FROM users")
    total_referrals = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT SUM(referral_bonus) FROM users")
    total_referral_bonus = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE is_active = 1")
    active_tasks = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM seasons WHERE is_active = 1")
    active_seasons = cursor.fetchone()[0]
    
    # Статистика за сегодня
    cursor.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at) = DATE('now')")
    new_users_today = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM user_tasks WHERE DATE(completed_at) = DATE('now')")
    tasks_completed_today = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT SUM(total_clicks) FROM users WHERE DATE(last_activity) = DATE('now')")
    clicks_today = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT SUM(stars) FROM users WHERE DATE(last_activity) = DATE('now')")
    stars_earned_today = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE DATE(last_activity) = DATE('now')")
    active_users_today = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE DATE(created_at) = DATE('now')")
    new_tickets_today = cursor.fetchone()[0] or 0
    
    # Статистика поддержки
    try:
        cursor.execute("SELECT COUNT(*) FROM support_tickets")
        total_tickets = cursor.fetchone()[0] or 0
    except:
        total_tickets = 0

    try:
        cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE status IN ('open', 'in_progress', 'waiting_admin')")
        open_support_tickets = cursor.fetchone()[0] or 0
    except:
        open_support_tickets = 0

    try:
        cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE status = 'waiting_user'")
        waiting_user_support_tickets = cursor.fetchone()[0] or 0
    except:
        waiting_user_support_tickets = 0

    try:
        cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE status = 'closed'")
        closed_support_tickets = cursor.fetchone()[0] or 0
    except:
        closed_support_tickets = 0
    
    # Топы и регистрации (без кэша, относительно дешёвые запросы)
    cursor.execute("""
        SELECT telegram_id, username, first_name, stars, click_coins, crystals, total_clicks, tasks_completed, referrals_count, is_banned
        FROM users 
        WHERE is_banned = 0
        ORDER BY stars DESC 
        LIMIT 10
    """)
    top_users = cursor.fetchall()
    
    cursor.execute("""
        SELECT telegram_id, username, first_name, total_clicks, stars, is_banned
        FROM users 
        WHERE is_banned = 0
        ORDER BY total_clicks DESC 
        LIMIT 10
    """)
    top_clickers = cursor.fetchall()
    
    cursor.execute("""
        SELECT telegram_id, username, first_name, referrals_count, referral_bonus, is_banned
        FROM users 
        WHERE is_banned = 0
        ORDER BY referrals_count DESC 
        LIMIT 10
    """)
    top_referrers = cursor.fetchall()
    
    cursor.execute("""
        SELECT telegram_id, username, first_name, created_at, is_banned
        FROM users 
        ORDER BY id DESC 
        LIMIT 10
    """)
    recent_users = cursor.fetchall()

    # Данные для графиков (активность за последние 7 дней) с кэшем Redis
    days = []
    new_users_chart = []
    tasks_chart = []
    clicks_chart = []

    chart_days_json = None
    chart_new_users_json = None
    chart_tasks_json = None
    chart_clicks_json = None

    r = get_redis_client()
    if r:
        try:
            cached = r.get("dashboard:charts")
        except Exception:
            cached = None
        if cached:
            try:
                cached_obj = json.loads(cached)
                chart_days_json = cached_obj.get("days")
                chart_new_users_json = cached_obj.get("new_users")
                chart_tasks_json = cached_obj.get("tasks")
                chart_clicks_json = cached_obj.get("clicks")
            except Exception:
                chart_days_json = None

    if chart_days_json is None:
        # Кэш отсутствует – считаем заново
        for i in range(6, -1, -1):
            day = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            days.append((datetime.now() - timedelta(days=i)).strftime('%d.%m'))
            
            cursor.execute(
                "SELECT COUNT(*) FROM users WHERE DATE(created_at) = DATE(?)",
                (day,),
            )
            new_users_chart.append(cursor.fetchone()[0] or 0)
            
            cursor.execute(
                "SELECT COUNT(*) FROM user_tasks WHERE DATE(completed_at) = DATE(?)",
                (day,),
            )
            tasks_chart.append(cursor.fetchone()[0] or 0)
            
            cursor.execute(
                "SELECT SUM(total_clicks) FROM users WHERE DATE(last_activity) = DATE(?)",
                (day,),
            )
            clicks_chart.append(cursor.fetchone()[0] or 0)

        chart_days_json = json.dumps(days)
        chart_new_users_json = json.dumps(new_users_chart)
        chart_tasks_json = json.dumps(tasks_chart)
        chart_clicks_json = json.dumps(clicks_chart)

        if r:
            try:
                r.setex(
                    "dashboard:charts",
                    60,
                    json.dumps(
                        {
                            "days": chart_days_json,
                            "new_users": chart_new_users_json,
                            "tasks": chart_tasks_json,
                            "clicks": chart_clicks_json,
                        }
                    ),
                )
            except Exception:
                pass

    conn.close()
    
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "page": "dashboard",
        
        # Общая статистика
        "total_users": total_users,
        "active_users": active_users,
        "banned_users": banned_users,
        "total_coins": f"{total_coins:,}".replace(",", " "),
        "total_stars": f"{total_stars:,}".replace(",", " "),
        "total_crystals": f"{total_crystals:,}".replace(",", " "),
        "total_clicks": f"{total_clicks:,}".replace(",", " "),
        "total_tasks": f"{total_tasks:,}".replace(",", " "),
        "total_referrals": total_referrals,
        "total_referral_bonus": f"{total_referral_bonus:,}".replace(",", " "),
        "active_tasks": active_tasks,
        "active_seasons": active_seasons,
        
        # Статистика за сегодня
        "new_users_today": new_users_today,
        "tasks_completed_today": tasks_completed_today,
        "clicks_today": f"{clicks_today:,}".replace(",", " "),
        "stars_earned_today": f"{stars_earned_today:,}".replace(",", " "),
        "active_users_today": active_users_today,
        "new_tickets_today": new_tickets_today,
        
        # Статистика поддержки
        "total_tickets": total_tickets,
        "open_support_tickets": open_support_tickets,
        "waiting_user_support_tickets": waiting_user_support_tickets,
        "closed_support_tickets": closed_support_tickets,
        
        # Топы
        "top_users": top_users,
        "top_clickers": top_clickers,
        "top_referrers": top_referrers,
        "recent_users": recent_users,
        
        # Данные для графиков (уже в JSON)
        "chart_days": chart_days_json,
        "chart_new_users": chart_new_users_json,
        "chart_tasks": chart_tasks_json,
        "chart_clicks": chart_clicks_json
    })

# Страница пользователей
@app.get("/users", response_class=HTMLResponse)
async def users_page(
    request: Request, 
    auth: str = Depends(verify_auth),
    search: str = Query(None),
    status: str = Query(None),
    sort: str = Query("id_desc")
):
    conn = sqlite3.connect('redpulse.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Базовый запрос
    query = """
        SELECT id, telegram_id, username, first_name, stars, click_coins, crystals, 
               referrals_count, total_clicks, tasks_completed, is_banned, ban_reason, ban_expires, created_at
        FROM users 
        WHERE 1=1
    """
    params = []
    
    # Фильтры
    if search:
        query += " AND (username LIKE ? OR first_name LIKE ? OR telegram_id LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    
    if status == "banned":
        query += " AND is_banned = 1"
    elif status == "active":
        query += " AND is_banned = 0"
    
    # Сортировка
    sort_map = {
        "id_desc": "id DESC",
        "id_asc": "id ASC",
        "stars_desc": "stars DESC",
        "stars_asc": "stars ASC",
        "clicks_desc": "total_clicks DESC",
        "clicks_asc": "total_clicks ASC",
        "date_desc": "created_at DESC",
        "date_asc": "created_at ASC"
    }
    query += f" ORDER BY {sort_map.get(sort, 'id DESC')}"
    
    cursor.execute(query, params)
    users = cursor.fetchall()
    
    # Статистика для фильтров
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users_all = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
    total_banned = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 0")
    total_active = cursor.fetchone()[0] or 0
    
    open_support_tickets = get_support_stats()
    
    conn.close()
    
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "page": "users",
        "users": users,
        "total_users_all": total_users_all,
        "total_banned": total_banned,
        "total_active": total_active,
        "current_search": search,
        "current_status": status,
        "current_sort": sort,
        "open_support_tickets": open_support_tickets
    })


@app.get("/users/view/{user_id}", response_class=HTMLResponse)
async def user_view_page(request: Request, user_id: int, auth: str = Depends(verify_auth)):
    open_support_tickets = get_support_stats()
    conn = sqlite3.connect("redpulse.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return RedirectResponse(url="/users?error=Пользователь не найден", status_code=303)

    # support tickets
    try:
        cursor.execute(
            "SELECT id, status, ticket_type, subject, created_at, last_activity FROM support_tickets WHERE user_id = ? ORDER BY id DESC LIMIT 10",
            (user_id,),
        )
        support_tickets = cursor.fetchall()
    except:
        support_tickets = []

    # notices
    try:
        cursor.execute(
            "SELECT id, notice_type, status, subject, created_at, last_activity FROM user_notices WHERE user_id = ? ORDER BY id DESC LIMIT 10",
            (user_id,),
        )
        notices = cursor.fetchall()
    except:
        notices = []

    # clan
    try:
        cursor.execute(
            "SELECT c.id, c.name, c.tag, cm.role FROM clan_members cm JOIN clans c ON c.id = cm.clan_id WHERE cm.user_id = ? LIMIT 1",
            (user_id,),
        )
        clan = cursor.fetchone()
    except:
        clan = None

    conn.close()
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "page": "user_view",
            "open_support_tickets": open_support_tickets,
            "u": user,
            "support_tickets": support_tickets,
            "notices": notices,
            "clan": clan,
        },
    )

# Бан пользователя
@app.post("/users/ban/{user_id}")
async def ban_user(
    request: Request,
    user_id: int,
    auth: str = Depends(verify_auth),
    ban_duration: str = Form(...),
    ban_reason: str = Form(...)
):
    conn = sqlite3.connect('redpulse.db')
    cursor = conn.cursor()
    
    ban_expires = None
    if ban_duration != "forever":
        days = int(ban_duration)
        ban_expires = (datetime.now() + timedelta(days=days)).isoformat()
    
    cursor.execute("""
        UPDATE users 
        SET is_banned = 1, ban_reason = ?, ban_expires = ?, banned_at = ?
        WHERE telegram_id = ?
    """, (ban_reason, ban_expires, datetime.now().isoformat(), user_id))
    
    conn.commit()
    conn.close()
    
    try:
        with open("bans.json", "r", encoding="utf-8") as f:
            bans = json.load(f)
    except:
        bans = []
    
    bans.append({
        "user_id": user_id,
        "reason": ban_reason,
        "expires": ban_expires,
        "banned_at": datetime.now().isoformat()
    })
    
    with open("bans.json", "w", encoding="utf-8") as f:
        json.dump(bans, f, ensure_ascii=False, indent=2)
    
    return RedirectResponse(url="/users", status_code=303)

# Разбан пользователя
@app.post("/users/unban/{user_id}")
async def unban_user(
    request: Request,
    user_id: int,
    auth: str = Depends(verify_auth)
):
    conn = sqlite3.connect('redpulse.db')
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE users 
        SET is_banned = 0, ban_reason = NULL, ban_expires = NULL, banned_at = NULL
        WHERE telegram_id = ?
    """, (user_id,))
    
    conn.commit()
    conn.close()
    
    return RedirectResponse(url="/users", status_code=303)

# Выдача валюты
@app.post("/users/give_currency/{user_id}")
async def give_currency(
    request: Request,
    user_id: int,
    auth: str = Depends(verify_auth),
    _: None = Depends(give_currency_rate_limit),
    currency_type: str = Form(...),
    amount: int = Form(...),
    reason: str = Form(...)
):
    MAX_VALUE = 1_000_000_000
    
    if amount > MAX_VALUE:
        return RedirectResponse(
            url=f"/users?error=Сумма слишком большая! Максимум {MAX_VALUE}", 
            status_code=303
        )
    
    if amount < 0:
        return RedirectResponse(
            url=f"/users?error=Сумма не может быть отрицательной", 
            status_code=303
        )
    
    conn = sqlite3.connect('redpulse.db')
    cursor = conn.cursor()
    
    if currency_type == "coins":
        cursor.execute("UPDATE users SET click_coins = click_coins + ? WHERE telegram_id = ?", (amount, user_id))
    elif currency_type == "stars":
        cursor.execute("UPDATE users SET stars = stars + ? WHERE telegram_id = ?", (amount, user_id))
    elif currency_type == "crystals":
        cursor.execute("UPDATE users SET crystals = crystals + ? WHERE telegram_id = ?", (amount, user_id))
    
    conn.commit()
    conn.close()
    
    try:
        with open("rewards.json", "r", encoding="utf-8") as f:
            rewards = json.load(f)
    except:
        rewards = []
    
    rewards.append({
        "user_id": user_id,
        "currency": currency_type,
        "amount": amount,
        "reason": reason,
        "given_at": datetime.now().isoformat()
    })
    
    with open("rewards.json", "w", encoding="utf-8") as f:
        json.dump(rewards, f, ensure_ascii=False, indent=2)
    
    return RedirectResponse(url="/users", status_code=303)

# ========== ЗАДАНИЯ ==========

# Страница заданий
@app.get("/tasks", response_class=HTMLResponse)
async def tasks_page(request: Request, auth: str = Depends(verify_auth)):
    conn = sqlite3.connect('redpulse.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM tasks ORDER BY id DESC")
    tasks_rows = cursor.fetchall()
    
    # Преобразуем Row в словари для JSON
    tasks = []
    for row in tasks_rows:
        task_dict = dict(row)
        # Преобразуем даты в строки
        if task_dict.get('created_at'):
            task_dict['created_at'] = str(task_dict['created_at'])
        tasks.append(task_dict)
    
    open_support_tickets = get_support_stats()
    
    conn.close()
    
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "page": "tasks",
        "tasks": tasks,
        "open_support_tickets": open_support_tickets,
        "edit_task": None
    })

# Получение данных задания для редактирования
@app.get("/tasks/edit/{task_id}")
async def get_task_for_edit(task_id: int, request: Request, auth: str = Depends(verify_auth)):
    conn = sqlite3.connect('redpulse.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    task_row = cursor.fetchone()
    
    # Преобразуем Row в словарь
    task = None
    if task_row:
        task = dict(task_row)
        if task.get('created_at'):
            task['created_at'] = str(task['created_at'])
    
    cursor.execute("SELECT * FROM tasks ORDER BY id DESC")
    tasks_rows = cursor.fetchall()
    
    # Преобразуем все строки в словари
    tasks = []
    for row in tasks_rows:
        t = dict(row)
        if t.get('created_at'):
            t['created_at'] = str(t['created_at'])
        tasks.append(t)
    
    open_support_tickets = get_support_stats()
    
    conn.close()
    
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "page": "tasks",
        "tasks": tasks,
        "edit_task": task,
        "open_support_tickets": open_support_tickets
    })

def _validate_positive_int(value: int, field_name: str, max_value: int = 1_000_000_000) -> int:
    """
    Простая валидация числовых полей (безопасность от слишком больших / отрицательных значений).
    """
    try:
        value_int = int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"Некорректное значение поля {field_name}")
    if value_int < 0:
        raise HTTPException(status_code=400, detail=f"Поле {field_name} не может быть отрицательным")
    if value_int > max_value:
        raise HTTPException(status_code=400, detail=f"Поле {field_name} не может быть больше {max_value}")
    return value_int


# Создание задания
@app.post("/tasks/create")
async def create_task(
    request: Request,
    auth: str = Depends(verify_auth),
    title: str = Form(...),
    description: str = Form(""),
    task_type: str = Form(...),
    channel_id: str = Form(None),
    channel_url: str = Form(None),
    reward_coins: int = Form(10),
    reward_stars: int = Form(0),
    reward_crystals: int = Form(0),
    max_completions: int = Form(-1),
    cooldown_hours: int = Form(0),
    is_active: bool = Form(False)
):
    """
    Создание задания.

    Для текущей версии поддерживаем только задания типа "подписка на канал":
    - task_type должен быть "subscribe"
    - channel_id и channel_url обязательны и не могут быть пустыми.
    """
    # Разрешаем только задания подписки
    task_type = (task_type or "subscribe").strip()
    if task_type != "subscribe":
        task_type = "subscribe"

    channel_id = (channel_id or "").strip()
    channel_url = (channel_url or "").strip()

    if not channel_id or not channel_url:
        # Возвращаемся на страницу с сообщением об ошибке
        return RedirectResponse(
            url="/tasks?error=Укажите ID канала и ссылку для задания-подписки",
            status_code=303,
        )

    # Лимиты по наградам (защита от слишком больших чисел)
    reward_coins = _validate_positive_int(reward_coins, "🪙 Монеты")
    reward_stars = _validate_positive_int(reward_stars, "⭐ Звёзды")
    reward_crystals = _validate_positive_int(reward_crystals, "💎 Кристаллы")

    conn = sqlite3.connect('redpulse.db')
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO tasks 
        (title, description, task_type, channel_id, channel_url, reward_coins, reward_stars, reward_crystals, max_completions, cooldown_hours, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            title,
            description,
            task_type,
            channel_id,
            channel_url,
            reward_coins,
            reward_stars,
            reward_crystals,
            max_completions,
            cooldown_hours,
            1 if is_active else 0,
        ),
    )

    conn.commit()
    conn.close()

    return RedirectResponse(url="/tasks", status_code=303)

# Редактирование задания
@app.post("/tasks/edit/{task_id}")
async def edit_task(
    request: Request,
    task_id: int,
    auth: str = Depends(verify_auth),
    title: str = Form(...),
    description: str = Form(""),
    task_type: str = Form(...),
    channel_id: str = Form(None),
    channel_url: str = Form(None),
    reward_coins: int = Form(10),
    reward_stars: int = Form(0),
    reward_crystals: int = Form(0),
    max_completions: int = Form(-1),
    cooldown_hours: int = Form(0),
    is_active: bool = Form(False)
):
    """
    Редактирование задания.

    Сохраняем ту же логику, что и при создании:
    - только тип "subscribe";
    - channel_id и channel_url обязательны;
    - награды валидируются по диапазону.
    """
    task_type = (task_type or "subscribe").strip()
    if task_type != "subscribe":
        task_type = "subscribe"

    channel_id = (channel_id or "").strip()
    channel_url = (channel_url or "").strip()

    if not channel_id or not channel_url:
        return RedirectResponse(
            url="/tasks?error=Укажите ID канала и ссылку для задания-подписки",
            status_code=303,
        )

    reward_coins = _validate_positive_int(reward_coins, "🪙 Монеты")
    reward_stars = _validate_positive_int(reward_stars, "⭐ Звёзды")
    reward_crystals = _validate_positive_int(reward_crystals, "💎 Кристаллы")

    conn = sqlite3.connect('redpulse.db')
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE tasks 
        SET title = ?, description = ?, task_type = ?, channel_id = ?, channel_url = ?,
            reward_coins = ?, reward_stars = ?, reward_crystals = ?, max_completions = ?,
            cooldown_hours = ?, is_active = ?
        WHERE id = ?
        """,
        (
            title,
            description,
            task_type,
            channel_id,
            channel_url,
            reward_coins,
            reward_stars,
            reward_crystals,
            max_completions,
            cooldown_hours,
            1 if is_active else 0,
            task_id,
        ),
    )

    conn.commit()
    conn.close()

    return RedirectResponse(url="/tasks", status_code=303)

# Удаление задания
@app.post("/tasks/delete/{task_id}")
async def delete_task(
    request: Request,
    task_id: int,
    auth: str = Depends(verify_auth)
):
    conn = sqlite3.connect('redpulse.db')
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM user_tasks WHERE task_id = ?", (task_id,))
    cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    
    conn.commit()
    conn.close()
    
    return RedirectResponse(url="/tasks", status_code=303)

# ========== СЕЗОНЫ ==========

# Страница сезонов
@app.get("/seasons", response_class=HTMLResponse)
async def seasons_page(request: Request, auth: str = Depends(verify_auth)):
    conn = sqlite3.connect('redpulse.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM seasons ORDER BY id DESC")
    seasons_rows = cursor.fetchall()
    
    # Преобразуем Row в словари для JSON
    seasons = []
    for row in seasons_rows:
        season_dict = dict(row)
        # Преобразуем даты в строки
        if season_dict.get('start_date'):
            season_dict['start_date'] = str(season_dict['start_date'])
        if season_dict.get('end_date'):
            season_dict['end_date'] = str(season_dict['end_date'])
        if season_dict.get('created_at'):
            season_dict['created_at'] = str(season_dict['created_at'])
        seasons.append(season_dict)
    
    open_support_tickets = get_support_stats()
    
    conn.close()
    
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "page": "seasons",
        "seasons": seasons,
        "open_support_tickets": open_support_tickets,
        "edit_season": None
    })

# Получение данных сезона для редактирования
@app.get("/seasons/edit/{season_id}")
async def get_season_for_edit(season_id: int, request: Request, auth: str = Depends(verify_auth)):
    conn = sqlite3.connect('redpulse.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM seasons WHERE id = ?", (season_id,))
    season_row = cursor.fetchone()
    
    # Преобразуем Row в словарь
    season = None
    if season_row:
        season = dict(season_row)
        if season.get('start_date'):
            season['start_date'] = str(season['start_date'])
        if season.get('end_date'):
            season['end_date'] = str(season['end_date'])
        if season.get('created_at'):
            season['created_at'] = str(season['created_at'])
    
    cursor.execute("SELECT * FROM seasons ORDER BY id DESC")
    seasons_rows = cursor.fetchall()
    
    # Преобразуем все строки в словари
    seasons = []
    for row in seasons_rows:
        s = dict(row)
        if s.get('start_date'):
            s['start_date'] = str(s['start_date'])
        if s.get('end_date'):
            s['end_date'] = str(s['end_date'])
        if s.get('created_at'):
            s['created_at'] = str(s['created_at'])
        seasons.append(s)
    
    open_support_tickets = get_support_stats()
    
    conn.close()
    
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "page": "seasons",
        "seasons": seasons,
        "edit_season": season,
        "open_support_tickets": open_support_tickets
    })

def _parse_datetime(value: str, field: str) -> datetime:
    """
    Разбор строки даты/времени из формы (формат HTML input datetime-local).
    """
    try:
        # Формат: YYYY-MM-DDTHH:MM
        return datetime.fromisoformat(value)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Некорректная дата в поле {field}")


# Создание сезона
@app.post("/seasons/create")
async def create_season(
    request: Request,
    auth: str = Depends(verify_auth),
    name: str = Form(...),
    description: str = Form(""),
    start_date: str = Form(...),
    end_date: str = Form(...),
    prize_1st: str = Form(""),
    prize_2nd: str = Form(""),
    prize_3rd: str = Form(""),
    is_active: bool = Form(False)
):
    """
    Создание сезона с валидацией дат и возможностью немедленных уведомлений.

    - Дата окончания не может быть раньше даты начала.
    - Если установлен флаг "Активен" и дата старта уже наступила,
      уведомления будут отправлены сразу (без ожидания планировщика).
    """
    start_dt = _parse_datetime(start_date, "Дата начала")
    end_dt = _parse_datetime(end_date, "Дата окончания")

    if end_dt < start_dt:
        return RedirectResponse(
            url="/seasons?error=Дата окончания не может быть раньше даты начала",
            status_code=303,
        )

    conn = sqlite3.connect('redpulse.db')
    cursor = conn.cursor()

    # В БД храним даты в формате YYYY-MM-DD HH:MM:SS (без T), иначе SQLite сравнивает строки некорректно и уведомления не срабатывают.
    start_date_db = start_dt.strftime("%Y-%m-%d %H:%M:%S")
    end_date_db = end_dt.strftime("%Y-%m-%d %H:%M:%S")
    # В БД по умолчанию сезон создаём как неактивный.
    # Логику активации/уведомлений берёт на себя планировщик или ручной вызов.
    cursor.execute(
        """
        INSERT INTO seasons 
        (name, description, start_date, end_date, prize_1st, prize_2nd, prize_3rd, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, datetime('now'))
        """,
        (name, description, start_date_db, end_date_db, prize_1st, prize_2nd, prize_3rd),
    )
    season_id = cursor.lastrowid

    conn.commit()
    conn.close()

    # Если админ создал сезон сразу активным и его старт уже наступил,
    # запускаем проверку сезонов в цикле бота, чтобы не ждать следующей минуты.
    if is_active and start_dt <= datetime.now():
        try:
            from main import check_seasons_start_end  # импорт внутри функции, чтобы избежать циклов

            if bot_loop:
                asyncio.run_coroutine_threadsafe(check_seasons_start_end(), bot_loop)
        except Exception as e:
            print(f"Ошибка немедленного запуска check_seasons_start_end: {e}")

    return RedirectResponse(url="/seasons", status_code=303)

# Редактирование сезона
@app.post("/seasons/edit/{season_id}")
async def edit_season(
    request: Request,
    season_id: int,
    auth: str = Depends(verify_auth),
    name: str = Form(...),
    description: str = Form(""),
    start_date: str = Form(...),
    end_date: str = Form(...),
    prize_1st: str = Form(""),
    prize_2nd: str = Form(""),
    prize_3rd: str = Form(""),
    is_active: bool = Form(False)
):
    """
    Редактирование сезона с проверкой дат и возможностью
    "включить" сезон, если он уже должен идти.
    """
    start_dt = _parse_datetime(start_date, "Дата начала")
    end_dt = _parse_datetime(end_date, "Дата окончания")

    if end_dt < start_dt:
        return RedirectResponse(
            url="/seasons?error=Дата окончания не может быть раньше даты начала",
            status_code=303,
        )

    conn = sqlite3.connect('redpulse.db')
    cursor = conn.cursor()

    # В БД храним даты в формате YYYY-MM-DD HH:MM:SS для корректного сравнения в планировщике.
    start_date_db = start_dt.strftime("%Y-%m-%d %H:%M:%S")
    end_date_db = end_dt.strftime("%Y-%m-%d %H:%M:%S")
    # При редактировании управляем только полями;
    # статус is_active оставляем как есть, чтобы им управлял планировщик.
    cursor.execute(
        """
        UPDATE seasons 
        SET name = ?, description = ?, start_date = ?, end_date = ?,
            prize_1st = ?, prize_2nd = ?, prize_3rd = ?
        WHERE id = ?
        """,
        (name, description, start_date_db, end_date_db, prize_1st, prize_2nd, prize_3rd, season_id),
    )

    conn.commit()
    conn.close()

    # Если админ пометил сезон как активный и дата старта уже наступила,
    # принудительно запускаем проверку сезонов (уведомления).
    if is_active and start_dt <= datetime.now():
        try:
            from main import check_seasons_start_end

            if bot_loop:
                asyncio.run_coroutine_threadsafe(check_seasons_start_end(), bot_loop)
        except Exception as e:
            print(f"Ошибка немедленного запуска check_seasons_start_end: {e}")

    return RedirectResponse(url="/seasons", status_code=303)

# Удаление сезона
@app.post("/seasons/delete/{season_id}")
async def delete_season(
    request: Request,
    season_id: int,
    auth: str = Depends(verify_auth)
):
    conn = sqlite3.connect('redpulse.db')
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM season_ratings WHERE season_id = ?", (season_id,))
    cursor.execute("DELETE FROM seasons WHERE id = ?", (season_id,))
    
    conn.commit()
    conn.close()
    
    return RedirectResponse(url="/seasons", status_code=303)

# Страница рассылки
@app.get("/broadcast", response_class=HTMLResponse)
async def broadcast_page(request: Request, auth: str = Depends(verify_auth)):
    conn = sqlite3.connect('redpulse.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 0")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE DATE(last_activity) > DATE('now', '-7 days') AND is_banned = 0")
    active_week_users = cursor.fetchone()[0] or 0
    
    open_support_tickets = get_support_stats()
    # История рассылок
    try:
        with open("broadcasts.json", "r", encoding="utf-8") as f:
            broadcasts = json.load(f)
    except Exception:
        broadcasts = []
    
    conn.close()
    
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "page": "broadcast",
        "total_users": total_users,
        "active_week_users": active_week_users,
        "open_support_tickets": open_support_tickets,
        "broadcasts": list(reversed(broadcasts[-50:])),
    })

# Отправка рассылки
@app.post("/broadcast/send")
async def send_broadcast(
    request: Request,
    auth: str = Depends(verify_auth),
    _: None = Depends(broadcast_rate_limit),
    message: str = Form(...),
    recipients: str = Form("all")
):
    # Простая валидация сообщения рассылки
    text = (message or "").strip()
    if not text:
        return RedirectResponse(
            url="/broadcast?error=Текст сообщения не может быть пустым",
            status_code=303,
        )
    if len(text) > 4096:
        return RedirectResponse(
            url="/broadcast?error=Сообщение слишком длинное (максимум 4096 символов)",
            status_code=303,
        )

    broadcast_data = {
        "id": str(uuid.uuid4()),
        "message": message,
        "recipients": recipients,
        "created_at": datetime.now().isoformat(),
        "status": "pending"
    }
    
    try:
        with open("broadcasts.json", "r", encoding="utf-8") as f:
            broadcasts = json.load(f)
    except:
        broadcasts = []
    
    broadcasts.append(broadcast_data)
    
    with open("broadcasts.json", "w", encoding="utf-8") as f:
        json.dump(broadcasts, f, ensure_ascii=False, indent=2)
    
    return RedirectResponse(url="/broadcast?success=1", status_code=303)


@app.post("/broadcast/delete/{broadcast_id}")
async def delete_broadcast(broadcast_id: str, auth: str = Depends(verify_auth)):
    """Удалить рассылку у пользователей (по сохранённым message_id) и пометить в истории."""
    try:
        with open("broadcasts.json", "r", encoding="utf-8") as f:
            broadcasts = json.load(f)
    except Exception:
        broadcasts = []
    for b in broadcasts:
        if b.get("id") == broadcast_id:
            b["status"] = "delete_pending"
            b["delete_requested_at"] = datetime.now().isoformat()

    with open("broadcasts.json", "w", encoding="utf-8") as f:
        json.dump(broadcasts, f, ensure_ascii=False, indent=2)

    return RedirectResponse(url="/broadcast", status_code=303)


# ====== Промокоды ======
@app.get("/promocodes", response_class=HTMLResponse)
async def promocodes_page(request: Request, auth: str = Depends(verify_auth)):
    open_support_tickets = get_support_stats()
    conn = sqlite3.connect("redpulse.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, code, reward_coins, reward_stars, reward_crystals, max_uses, used_count, is_active, expires_at, created_at "
        "FROM promo_codes ORDER BY id DESC LIMIT 100"
    )
    promos = cursor.fetchall()
    conn.close()
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "page": "promocodes", "open_support_tickets": open_support_tickets, "promos": promos},
    )


@app.post("/promocodes/create")
async def promocodes_create(
    request: Request,
    auth: str = Depends(verify_auth),
    code: str = Form(...),
    reward_coins: int = Form(0),
    reward_stars: int = Form(0),
    reward_crystals: int = Form(0),
    max_uses: int = Form(1),
    expires_at: str = Form(""),
):
    c = (code or "").strip().upper()
    if not c or len(c) > 32:
        return RedirectResponse(url="/promocodes?error=Неверный код", status_code=303)
    reward_coins = max(0, min(int(reward_coins or 0), 1_000_000_000))
    reward_stars = max(0, min(int(reward_stars or 0), 1_000_000_000))
    reward_crystals = max(0, min(int(reward_crystals or 0), 1_000_000_000))
    max_uses = max(0, min(int(max_uses or 0), 1_000_000_000))
    exp = (expires_at or "").strip()
    if exp:
        # ожидаем YYYY-MM-DD HH:MM или YYYY-MM-DDTHH:MM
        exp = exp.replace("T", " ")[:16]
    conn = sqlite3.connect("redpulse.db")
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO promo_codes(code,reward_coins,reward_stars,reward_crystals,max_uses,used_count,is_active,expires_at) "
            "VALUES(?,?,?,?,?,0,1,?)",
            (c, reward_coins, reward_stars, reward_crystals, max_uses, exp or None),
        )
        conn.commit()
    except Exception:
        conn.close()
        return RedirectResponse(url="/promocodes?error=Код уже существует", status_code=303)
    conn.close()
    return RedirectResponse(url="/promocodes?success=1", status_code=303)


@app.post("/promocodes/toggle/{promo_id}")
async def promocodes_toggle(promo_id: int, auth: str = Depends(verify_auth)):
    conn = sqlite3.connect("redpulse.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE promo_codes SET is_active = CASE WHEN is_active=1 THEN 0 ELSE 1 END WHERE id = ?", (promo_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/promocodes", status_code=303)


@app.post("/promocodes/delete/{promo_id}")
async def promocodes_delete(promo_id: int, auth: str = Depends(verify_auth)):
    conn = sqlite3.connect("redpulse.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM promo_codes WHERE id = ?", (promo_id,))
    cursor.execute("DELETE FROM promo_redemptions WHERE promo_id = ?", (promo_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/promocodes", status_code=303)


# ====== Титулы и ачивки ======
@app.get("/titles", response_class=HTMLResponse)
async def titles_page(request: Request, auth: str = Depends(verify_auth)):
    open_support_tickets = get_support_stats()
    conn = sqlite3.connect("redpulse.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, code, name, description, category, is_active, created_at FROM titles ORDER BY id DESC LIMIT 200"
    )
    titles = cursor.fetchall()
    conn.close()
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "page": "titles", "open_support_tickets": open_support_tickets, "titles": titles},
    )


@app.post("/titles/create")
async def titles_create(
    request: Request,
    auth: str = Depends(verify_auth),
    code: str = Form(...),
    name: str = Form(...),
    description: str = Form(""),
    category: str = Form("admin"),
):
    c = (code or "").strip().upper()
    n = (name or "").strip()
    d = (description or "").strip()
    cat = (category or "admin").strip()
    if not c or len(c) > 64 or not n or len(n) > 128:
        return RedirectResponse(url="/titles?error=Неверные данные", status_code=303)
    conn = sqlite3.connect("redpulse.db")
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO titles(code,name,description,category,is_active,created_at) VALUES(?,?,?,?,1,datetime('now'))",
            (c, n, d, cat),
        )
        conn.commit()
    except Exception:
        conn.close()
        return RedirectResponse(url="/titles?error=Код уже существует", status_code=303)
    conn.close()
    return RedirectResponse(url="/titles?success=1", status_code=303)


@app.post("/titles/toggle/{title_id}")
async def titles_toggle(title_id: int, auth: str = Depends(verify_auth)):
    conn = sqlite3.connect("redpulse.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE titles SET is_active = CASE WHEN is_active=1 THEN 0 ELSE 1 END WHERE id = ?", (title_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/titles", status_code=303)


@app.post("/titles/grant")
async def titles_grant(
    request: Request,
    auth: str = Depends(verify_auth),
    user_id: int = Form(...),
    title_id: int = Form(...),
    set_current: bool = Form(False),
):
    conn = sqlite3.connect("redpulse.db")
    cursor = conn.cursor()
    # ensure user exists
    cursor.execute("SELECT telegram_id FROM users WHERE telegram_id = ?", (user_id,))
    if not cursor.fetchone():
        conn.close()
        return RedirectResponse(url="/titles?error=Пользователь не найден", status_code=303)
    # insert ownership (ignore duplicates)
    cursor.execute(
        "INSERT OR IGNORE INTO user_titles(user_id,title_id,obtained_at,source) VALUES(?,?,datetime('now'),'admin')",
        (user_id, title_id),
    )
    # Получаем имя титула для уведомления
    cursor.execute("SELECT name FROM titles WHERE id = ?", (title_id,))
    trow = cursor.fetchone()
    title_name = trow[0] if trow else "Титул"
    if set_current:
        try:
            cursor.execute("UPDATE users SET current_title_id = ? WHERE telegram_id = ?", (title_id, user_id))
        except Exception:
            pass
    conn.commit()
    conn.close()

    # Уведомление пользователю
    try:
        add_to_queue(
            int(user_id),
            f"🎖 **Тебе выдан титул!**\n\n"
            f"🏷 {title_name}\n\n"
            f"Посмотреть и выбрать: /titles",
            "Markdown",
        )
    except Exception:
        pass
    return RedirectResponse(url="/titles?success=1", status_code=303)


@app.get("/achievements", response_class=HTMLResponse)
async def achievements_page(request: Request, auth: str = Depends(verify_auth)):
    open_support_tickets = get_support_stats()
    conn = sqlite3.connect("redpulse.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, code, name, metric, threshold, reward_title_id, is_active, created_at FROM achievements ORDER BY id DESC LIMIT 200"
    )
    achs = cursor.fetchall()
    cursor.execute("SELECT id, name FROM titles WHERE is_active = 1 ORDER BY id DESC LIMIT 500")
    titles = cursor.fetchall()
    conn.close()
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "page": "achievements",
            "open_support_tickets": open_support_tickets,
            "achievements": achs,
            "titles": titles,
        },
    )


@app.post("/achievements/create")
async def achievements_create(
    request: Request,
    auth: str = Depends(verify_auth),
    code: str = Form(...),
    name: str = Form(...),
    metric: str = Form(...),
    threshold: int = Form(...),
    reward_title_id: int = Form(None),
):
    c = (code or "").strip().upper()
    n = (name or "").strip()
    m = (metric or "").strip()
    thr = max(0, min(int(threshold or 0), 2_000_000_000))
    if not c or len(c) > 64 or not n or len(n) > 128:
        return RedirectResponse(url="/achievements?error=Неверные данные", status_code=303)
    if m not in ("total_clicks", "streak_days", "stars", "xp", "level"):
        return RedirectResponse(url="/achievements?error=Неверная метрика", status_code=303)
    conn = sqlite3.connect("redpulse.db")
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO achievements(code,name,metric,threshold,reward_title_id,is_active,created_at) "
            "VALUES(?,?,?,?,?,1,datetime('now'))",
            (c, n, m, thr, reward_title_id),
        )
        conn.commit()
    except Exception:
        conn.close()
        return RedirectResponse(url="/achievements?error=Код уже существует", status_code=303)
    conn.close()
    return RedirectResponse(url="/achievements?success=1", status_code=303)


@app.post("/achievements/toggle/{achievement_id}")
async def achievements_toggle(achievement_id: int, auth: str = Depends(verify_auth)):
    conn = sqlite3.connect("redpulse.db")
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE achievements SET is_active = CASE WHEN is_active=1 THEN 0 ELSE 1 END WHERE id = ?",
        (achievement_id,),
    )
    conn.commit()
    conn.close()
    return RedirectResponse(url="/achievements", status_code=303)


# ====== Кланы и общая казна ======
@app.get("/clans", response_class=HTMLResponse)
async def clans_page(request: Request, auth: str = Depends(verify_auth)):
    open_support_tickets = get_support_stats()
    conn = sqlite3.connect("redpulse.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT c.id, c.name, c.tag, c.description, c.owner_id, c.treasury_coins, c.treasury_stars, c.treasury_crystals,
               c.war_schedule_json, c.is_active, c.created_at,
               (SELECT COUNT(*) FROM clan_members cm WHERE cm.clan_id = c.id) as members_count
        FROM clans c
        ORDER BY c.id DESC
        LIMIT 200
        """
    )
    clans = cursor.fetchall()
    conn.close()
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "page": "clans", "open_support_tickets": open_support_tickets, "clans": clans},
    )


@app.post("/clans/update/{clan_id}")
async def clans_update(
    clan_id: int,
    auth: str = Depends(verify_auth),
    description: str = Form(""),
    war_schedule_json: str = Form(""),
    treasury_coins: int = Form(0),
    treasury_stars: int = Form(0),
    treasury_crystals: int = Form(0),
):
    conn = sqlite3.connect("redpulse.db")
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE clans
        SET description = ?, war_schedule_json = ?, treasury_coins = ?, treasury_stars = ?, treasury_crystals = ?
        WHERE id = ?
        """,
        (
            (description or "").strip(),
            (war_schedule_json or "").strip() or None,
            max(0, int(treasury_coins or 0)),
            max(0, int(treasury_stars or 0)),
            max(0, int(treasury_crystals or 0)),
            clan_id,
        ),
    )
    conn.commit()
    conn.close()
    return RedirectResponse(url="/clans?success=1", status_code=303)


@app.post("/clans/toggle/{clan_id}")
async def clans_toggle(clan_id: int, auth: str = Depends(verify_auth)):
    conn = sqlite3.connect("redpulse.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE clans SET is_active = CASE WHEN is_active=1 THEN 0 ELSE 1 END WHERE id = ?", (clan_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/clans", status_code=303)


@app.post("/clans/delete/{clan_id}")
async def clans_delete(clan_id: int, auth: str = Depends(verify_auth)):
    conn = sqlite3.connect("redpulse.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM clan_members WHERE clan_id = ?", (clan_id,))
    cursor.execute("DELETE FROM clans WHERE id = ?", (clan_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/clans", status_code=303)


@app.get("/bank", response_class=HTMLResponse)
async def bank_page(request: Request, auth: str = Depends(verify_auth)):
    open_support_tickets = get_support_stats()
    conn = sqlite3.connect("redpulse.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO global_bank(id, coins, xp, level, target) VALUES(1, 0, 0, 1, 100000)")
    conn.commit()
    cursor.execute("SELECT id, coins, xp, level, target, bonus_active_until, updated_at FROM global_bank WHERE id = 1")
    bank = cursor.fetchone()
    conn.close()
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "page": "bank", "open_support_tickets": open_support_tickets, "bank": bank},
    )


@app.post("/bank/update")
async def bank_update(
    request: Request,
    auth: str = Depends(verify_auth),
    coins: int = Form(0),
    xp: int = Form(0),
    level: int = Form(1),
    target: int = Form(100000),
    bonus_active_until: str = Form(""),
):
    coins = max(0, min(int(coins or 0), 2_000_000_000))
    xp = max(0, min(int(xp or 0), 2_000_000_000))
    level = max(1, min(int(level or 1), 1_000_000))
    target = max(1, min(int(target or 100000), 2_000_000_000))
    bau = (bonus_active_until or "").strip()
    if bau:
        bau = bau.replace("T", " ")[:19]
    else:
        bau = None
    conn = sqlite3.connect("redpulse.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO global_bank(id, coins, xp, level, target) VALUES(1, 0, 0, 1, 100000)")
    cursor.execute(
        "UPDATE global_bank SET coins = ?, xp = ?, level = ?, target = ?, bonus_active_until = ? WHERE id = 1",
        (coins, xp, level, target, bau),
    )
    conn.commit()
    conn.close()
    return RedirectResponse(url="/bank?success=1", status_code=303)


@app.get("/wheel", response_class=HTMLResponse)
async def wheel_page(request: Request, auth: str = Depends(verify_auth)):
    open_support_tickets = get_support_stats()
    conn = sqlite3.connect("redpulse.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO wheel_config(id, cooldown_hours, is_active) VALUES(1, 24, 1)")
    conn.commit()
    cursor.execute("SELECT id, segments_json, cooldown_hours, is_active, updated_at FROM wheel_config WHERE id = 1")
    wheel = cursor.fetchone()
    conn.close()
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "page": "wheel", "open_support_tickets": open_support_tickets, "wheel": wheel},
    )


@app.post("/wheel/update")
async def wheel_update(
    request: Request,
    auth: str = Depends(verify_auth),
    preset: str = Form("default"),
    cooldown_hours: int = Form(24),
    is_active: bool = Form(False),
):
    cooldown_hours = max(1, min(int(cooldown_hours or 24), 168))
    p = (preset or "default").strip().lower()

    # Пресеты (без ручного JSON)
    if p == "default":
        sj = json.dumps(
            [
                {"code": "COINS_SMALL", "label": "🪙 +150", "weight": 40, "reward": {"coins": 150}},
                {"code": "COINS_MED", "label": "🪙 +400", "weight": 22, "reward": {"coins": 400}},
                {"code": "XP_SMALL", "label": "⭐ XP +60", "weight": 18, "reward": {"xp": 60}},
                {"code": "CRYSTAL", "label": "💎 +1", "weight": 8, "reward": {"crystals": 1}},
                {"code": "STARS", "label": "⭐ +2", "weight": 6, "reward": {"stars": 2}},
                {"code": "JACKPOT", "label": "💰 Джекпот (🪙 +2000)", "weight": 6, "reward": {"coins": 2000}},
            ],
            ensure_ascii=False,
        )
    elif p == "easy":
        sj = json.dumps(
            [
                {"code": "COINS_SMALL", "label": "🪙 +250", "weight": 45, "reward": {"coins": 250}},
                {"code": "COINS_MED", "label": "🪙 +700", "weight": 25, "reward": {"coins": 700}},
                {"code": "XP_SMALL", "label": "⭐ XP +100", "weight": 18, "reward": {"xp": 100}},
                {"code": "CRYSTAL", "label": "💎 +1", "weight": 8, "reward": {"crystals": 1}},
                {"code": "STARS", "label": "⭐ +3", "weight": 3, "reward": {"stars": 3}},
                {"code": "JACKPOT", "label": "💰 Джекпот (🪙 +4000)", "weight": 1, "reward": {"coins": 4000}},
            ],
            ensure_ascii=False,
        )
    elif p == "hard":
        sj = json.dumps(
            [
                {"code": "COINS_SMALL", "label": "🪙 +80", "weight": 50, "reward": {"coins": 80}},
                {"code": "COINS_MED", "label": "🪙 +250", "weight": 25, "reward": {"coins": 250}},
                {"code": "XP_SMALL", "label": "⭐ XP +40", "weight": 17, "reward": {"xp": 40}},
                {"code": "CRYSTAL", "label": "💎 +1", "weight": 6, "reward": {"crystals": 1}},
                {"code": "STARS", "label": "⭐ +1", "weight": 2, "reward": {"stars": 1}},
            ],
            ensure_ascii=False,
        )
    else:
        # fallback
        sj = None
    conn = sqlite3.connect("redpulse.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO wheel_config(id, cooldown_hours, is_active) VALUES(1, 24, 1)")
    cursor.execute(
        "UPDATE wheel_config SET segments_json = ?, cooldown_hours = ?, is_active = ? WHERE id = 1",
        (sj or None, cooldown_hours, 1 if is_active else 0),
    )
    conn.commit()
    conn.close()
    return RedirectResponse(url="/wheel?success=1", status_code=303)


@app.get("/auction", response_class=HTMLResponse)
async def auction_page(request: Request, auth: str = Depends(verify_auth)):
    open_support_tickets = get_support_stats()
    conn = sqlite3.connect("redpulse.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, description, start_at, end_at, min_bid, status, winner_user_id, winner_bid, created_at "
        "FROM auction_lots ORDER BY id DESC LIMIT 100"
    )
    lots = cursor.fetchall()
    conn.close()
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "page": "auction", "open_support_tickets": open_support_tickets, "lots": lots},
    )


@app.post("/auction/create")
async def auction_create(
    request: Request,
    auth: str = Depends(verify_auth),
    name: str = Form(...),
    description: str = Form(""),
    duration_hours: int = Form(24),
    min_bid: int = Form(0),
):
    n = (name or "").strip()
    d = (description or "").strip()
    duration_hours = max(1, min(int(duration_hours or 24), 168))
    min_bid = max(0, min(int(min_bid or 0), 2_000_000_000))
    if not n or len(n) > 128:
        return RedirectResponse(url="/auction?error=Неверное имя", status_code=303)
    start_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    end_at = (datetime.now() + timedelta(hours=duration_hours)).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect("redpulse.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO auction_lots(name, description, start_at, end_at, min_bid, status, winner_user_id, winner_bid, created_at) "
        "VALUES(?,?,?,?,?,'active',NULL,0,datetime('now'))",
        (n, d, start_at, end_at, min_bid),
    )
    conn.commit()
    conn.close()
    return RedirectResponse(url="/auction?success=1", status_code=303)


@app.post("/auction/close/{lot_id}")
async def auction_close(lot_id: int, auth: str = Depends(verify_auth)):
    conn = sqlite3.connect("redpulse.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE auction_lots SET status = 'closed' WHERE id = ?", (lot_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/auction", status_code=303)


@app.get("/events", response_class=HTMLResponse)
async def events_page(request: Request, auth: str = Depends(verify_auth)):
    open_support_tickets = get_support_stats()
    conn = sqlite3.connect("redpulse.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, code, name, description, start_at, end_at, settings_json, is_active, created_at "
        "FROM events ORDER BY id DESC LIMIT 200"
    )
    events = cursor.fetchall()
    conn.close()
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "page": "events", "open_support_tickets": open_support_tickets, "events": events},
    )


@app.post("/events/create")
async def events_create(
    request: Request,
    auth: str = Depends(verify_auth),
    code: str = Form(...),
    name: str = Form(...),
    description: str = Form(""),
    start_at: str = Form(""),
    end_at: str = Form(""),
    settings_json: str = Form(""),
    is_active: bool = Form(False),
):
    c = (code or "").strip().upper()
    n = (name or "").strip()
    d = (description or "").strip()
    s = (start_at or "").strip().replace("T", " ")[:19]
    e = (end_at or "").strip().replace("T", " ")[:19]
    sj = (settings_json or "").strip()
    if sj:
        try:
            json.loads(sj)
        except Exception:
            return RedirectResponse(url="/events?error=Неверный JSON", status_code=303)
    if not c or len(c) > 64 or not n or len(n) > 128:
        return RedirectResponse(url="/events?error=Неверные данные", status_code=303)
    conn = sqlite3.connect("redpulse.db")
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO events(code,name,description,start_at,end_at,settings_json,is_active,created_at) "
            "VALUES(?,?,?,?,?,?,?,datetime('now'))",
            (c, n, d, s or None, e or None, sj or None, 1 if is_active else 0),
        )
        conn.commit()
    except Exception:
        conn.close()
        return RedirectResponse(url="/events?error=Код уже существует", status_code=303)
    conn.close()
    return RedirectResponse(url="/events?success=1", status_code=303)


@app.post("/events/toggle/{event_id}")
async def events_toggle(event_id: int, auth: str = Depends(verify_auth)):
    conn = sqlite3.connect("redpulse.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE events SET is_active = CASE WHEN is_active=1 THEN 0 ELSE 1 END WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/events", status_code=303)


# ========== ЭКСТРЕННЫЕ СООБЩЕНИЯ / ПРЕДУПРЕЖДЕНИЯ ==========
@app.get("/notices", response_class=HTMLResponse)
async def notices_page(
    request: Request,
    auth: str = Depends(verify_auth),
    view: str = Query("active"),
    notice_id: int = Query(None),
):
    open_support_tickets = get_support_stats()
    conn = sqlite3.connect("redpulse.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    # safety: ensure tables exist
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_notices(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                notice_type TEXT NOT NULL DEFAULT 'message',
                status TEXT NOT NULL DEFAULT 'open',
                subject TEXT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                last_activity TEXT DEFAULT (datetime('now')),
                closed_at TEXT NULL,
                closed_by TEXT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_notice_messages(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                notice_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                sender_type TEXT NOT NULL,
                message TEXT NOT NULL,
                is_read INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()
    except Exception:
        pass

    if view == "closed":
        cursor.execute(
            "SELECT * FROM user_notices WHERE status = 'closed' ORDER BY last_activity DESC LIMIT 100"
        )
    else:
        cursor.execute(
            "SELECT * FROM user_notices WHERE status != 'closed' ORDER BY last_activity DESC LIMIT 200"
        )
    notices = cursor.fetchall()

    selected_notice = None
    messages = []
    if notice_id:
        cursor.execute("SELECT * FROM user_notices WHERE id = ?", (notice_id,))
        selected_notice = cursor.fetchone()
        if selected_notice:
            cursor.execute(
                "UPDATE user_notice_messages SET is_read = 1 WHERE notice_id = ? AND sender_type = 'user'",
                (notice_id,),
            )
            conn.commit()
            cursor.execute(
                "SELECT * FROM user_notice_messages WHERE notice_id = ? ORDER BY created_at ASC",
                (notice_id,),
            )
            messages = cursor.fetchall()

    conn.close()
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "page": "notices",
            "open_support_tickets": open_support_tickets,
            "notices": notices,
            "current_view": view,
            "selected_notice": selected_notice,
            "notice_messages": messages,
        },
    )


@app.post("/notices/create")
async def notices_create(
    request: Request,
    auth: str = Depends(verify_auth),
    user_id: int = Form(...),
    notice_type: str = Form("message"),
    subject: str = Form(""),
    message: str = Form(...),
):
    nt = (notice_type or "message").strip().lower()
    if nt not in ("message", "warning"):
        nt = "message"
    subj = (subject or "").strip()[:128]
    text = (message or "").strip()
    if not text:
        return RedirectResponse(url="/notices?error=Пустое сообщение", status_code=303)

    conn = sqlite3.connect("redpulse.db")
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_id FROM users WHERE telegram_id = ?", (user_id,))
    if not cursor.fetchone():
        conn.close()
        return RedirectResponse(url="/notices?error=Пользователь не найден", status_code=303)

    cursor.execute(
        "INSERT INTO user_notices(user_id, notice_type, status, subject, created_at, last_activity) "
        "VALUES(?, ?, 'waiting_user', ?, datetime('now'), datetime('now'))",
        (user_id, nt, subj or None),
    )
    nid = cursor.lastrowid
    cursor.execute(
        "INSERT INTO user_notice_messages(notice_id, user_id, sender_type, message, is_read, created_at) "
        "VALUES(?, ?, 'admin', ?, 0, datetime('now'))",
        (nid, user_id, text),
    )
    if nt == "warning":
        try:
            cursor.execute("UPDATE users SET warnings_count = COALESCE(warnings_count,0) + 1 WHERE telegram_id = ?", (user_id,))
        except Exception:
            pass
    conn.commit()
    conn.close()

    # уведомление пользователю
    try:
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        kb = InlineKeyboardBuilder()
        kb.button(text="📋 История", callback_data=f"notice_view_{nid}")
        kb.button(text="✏️ Ответить", callback_data=f"notice_reply_{nid}")
        kb.adjust(1)
        add_to_queue(
            int(user_id),
            ("⚠️ **Предупреждение от администрации**\n\n" if nt == "warning" else "📩 **Сообщение от администрации**\n\n")
            + (f"Тема: *{subj}*\n\n" if subj else "")
            + text,
            "Markdown",
            kb.as_markup(),
        )
    except Exception:
        pass

    return RedirectResponse(url=f"/notices?success=1&notice_id={nid}", status_code=303)


@app.post("/notices/send/{notice_id}")
async def notices_send(
    notice_id: int,
    request: Request,
    auth: str = Depends(verify_auth),
    message: str = Form(...),
):
    text = (message or "").strip()
    if not text:
        return RedirectResponse(url=f"/notices?notice_id={notice_id}&error=Пустое сообщение", status_code=303)
    conn = sqlite3.connect("redpulse.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_notices WHERE id = ?", (notice_id,))
    n = cursor.fetchone()
    if not n:
        conn.close()
        return RedirectResponse(url="/notices?error=Тикет не найден", status_code=303)
    if n["status"] == "closed":
        conn.close()
        return RedirectResponse(url=f"/notices?notice_id={notice_id}&error=Тикет закрыт", status_code=303)

    cursor.execute(
        "INSERT INTO user_notice_messages(notice_id, user_id, sender_type, message, is_read, created_at) "
        "VALUES(?, ?, 'admin', ?, 0, datetime('now'))",
        (notice_id, int(n["user_id"]), text),
    )
    cursor.execute(
        "UPDATE user_notices SET status = 'waiting_user', last_activity = datetime('now') WHERE id = ?",
        (notice_id,),
    )
    conn.commit()
    conn.close()

    try:
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        kb = InlineKeyboardBuilder()
        kb.button(text="📋 История", callback_data=f"notice_view_{notice_id}")
        kb.button(text="✏️ Ответить", callback_data=f"notice_reply_{notice_id}")
        kb.adjust(1)
        add_to_queue(
            int(n["user_id"]),
            "📩 **Новое сообщение от администрации**\n\n" + text,
            "Markdown",
            kb.as_markup(),
        )
    except Exception:
        pass

    return RedirectResponse(url=f"/notices?notice_id={notice_id}&success=1", status_code=303)


@app.post("/notices/close/{notice_id}")
async def notices_close(notice_id: int, auth: str = Depends(verify_auth)):
    conn = sqlite3.connect("redpulse.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_notices WHERE id = ?", (notice_id,))
    n = cursor.fetchone()
    if not n:
        conn.close()
        return RedirectResponse(url="/notices?error=Тикет не найден", status_code=303)
    if n["status"] != "closed":
        cursor.execute(
            "UPDATE user_notices SET status='closed', closed_at=datetime('now'), closed_by='admin', last_activity=datetime('now') WHERE id = ?",
            (notice_id,),
        )
        conn.commit()
    conn.close()
    try:
        add_to_queue(
            int(n["user_id"]),
            f"✅ **Тикет #{notice_id} закрыт администратором**",
            "Markdown",
        )
    except Exception:
        pass
    return RedirectResponse(url="/notices", status_code=303)


# Страница статистики (детальная)
@app.get("/stats", response_class=HTMLResponse)
async def stats_page(request: Request, auth: str = Depends(verify_auth)):
    conn = sqlite3.connect('redpulse.db')
    cursor = conn.cursor()
    
    # Общая статистика
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
    banned_users = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 0")
    active_users = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT SUM(click_coins) FROM users")
    total_coins = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT SUM(stars) FROM users")
    total_stars = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT SUM(crystals) FROM users")
    total_crystals = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT SUM(total_clicks) FROM users")
    total_clicks = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT SUM(tasks_completed) FROM users")
    total_tasks = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT SUM(referrals_count) FROM users")
    total_referrals = cursor.fetchone()[0] or 0

    # Доп. статистика (уровни/streak/кланы/казна)
    avg_level = 1
    max_level = 1
    total_xp = 0
    total_streak = 0
    try:
        cursor.execute("SELECT AVG(level), MAX(level), SUM(xp), SUM(streak_days) FROM users WHERE is_banned = 0")
        row = cursor.fetchone() or (1, 1, 0, 0)
        avg_level = round(float(row[0] or 1), 2)
        max_level = int(row[1] or 1)
        total_xp = int(row[2] or 0)
        total_streak = int(row[3] or 0)
    except Exception:
        pass

    clans_count = 0
    clan_members = 0
    try:
        cursor.execute("SELECT COUNT(*) FROM clans WHERE is_active = 1")
        clans_count = int(cursor.fetchone()[0] or 0)
        cursor.execute("SELECT COUNT(*) FROM clan_members")
        clan_members = int(cursor.fetchone()[0] or 0)
    except Exception:
        pass

    bank_coins = 0
    bank_level = 1
    bank_target = 0
    try:
        cursor.execute("SELECT coins, level, target FROM global_bank WHERE id = 1")
        b = cursor.fetchone()
        if b:
            bank_coins = int(b[0] or 0)
            bank_level = int(b[1] or 1)
            bank_target = int(b[2] or 0)
    except Exception:
        pass
    
    # Статистика по дням
    daily_stats = []
    for i in range(6, -1, -1):
        day = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        day_name = (datetime.now() - timedelta(days=i)).strftime('%d.%m.%Y')
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at) = DATE(?)", (day,))
        new_users = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM user_tasks WHERE DATE(completed_at) = DATE(?)", (day,))
        tasks_done = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT SUM(total_clicks) FROM users WHERE DATE(last_activity) = DATE(?)", (day,))
        clicks_day = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE DATE(last_activity) = DATE(?)", (day,))
        active_day = cursor.fetchone()[0] or 0
        
        daily_stats.append({
            "date": day_name,
            "new_users": new_users,
            "tasks": tasks_done,
            "clicks": clicks_day,
            "active": active_day
        })
    
    # Статистика по валютам
    cursor.execute("""
        SELECT 
            SUM(CASE WHEN stars >= 1000 THEN 1 ELSE 0 END) as vip_users,
            SUM(CASE WHEN stars BETWEEN 500 AND 999 THEN 1 ELSE 0 END) as pro_users,
            SUM(CASE WHEN stars BETWEEN 100 AND 499 THEN 1 ELSE 0 END) as regular_users,
            SUM(CASE WHEN stars < 100 THEN 1 ELSE 0 END) as newbie_users
        FROM users WHERE is_banned = 0
    """)
    stats = cursor.fetchone()
    
    open_support_tickets = get_support_stats()
    
    conn.close()
    
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "page": "stats",
        
        # Общая статистика
        "total_users": total_users,
        "active_users": active_users,
        "banned_users": banned_users,
        "total_coins": f"{total_coins:,}".replace(",", " "),
        "total_stars": f"{total_stars:,}".replace(",", " "),
        "total_crystals": f"{total_crystals:,}".replace(",", " "),
        "total_clicks": f"{total_clicks:,}".replace(",", " "),
        "total_tasks": f"{total_tasks:,}".replace(",", " "),
        "total_referrals": total_referrals,

        # Доп. статистика
        "avg_level": avg_level,
        "max_level": max_level,
        "total_xp": f"{total_xp:,}".replace(",", " "),
        "total_streak": f"{total_streak:,}".replace(",", " "),
        "clans_count": clans_count,
        "clan_members": clan_members,
        "bank_coins": f"{bank_coins:,}".replace(",", " "),
        "bank_level": bank_level,
        "bank_target": f"{bank_target:,}".replace(",", " "),
        
        # Статистика по дням
        "daily_stats": daily_stats,
        
        # Распределение пользователей
        "vip_users": stats[0] or 0,
        "pro_users": stats[1] or 0,
        "regular_users": stats[2] or 0,
        "newbie_users": stats[3] or 0,
        
        "open_support_tickets": open_support_tickets
    })

# Страница логов
@app.get("/logs", response_class=HTMLResponse)
async def logs_page(
    request: Request, 
    auth: str = Depends(verify_auth),
    type: str = Query(None),
    days: int = Query(7)
):
    open_support_tickets = get_support_stats()
    
    # Собираем реальные логи из разных источников
    logs = []
    
    # Логи банов
    try:
        with open("bans.json", "r", encoding="utf-8") as f:
            bans = json.load(f)
            for ban in bans[-50:]:
                time = datetime.fromisoformat(ban['banned_at']).strftime('%Y-%m-%d %H:%M')
                logs.append({
                    "time": time,
                    "type": "ban",
                    "user_id": ban['user_id'],
                    "action": "Бан пользователя",
                    "details": f"Причина: {ban['reason']}"
                })
    except:
        pass
    
    # Логи выдач валюты
    try:
        with open("rewards.json", "r", encoding="utf-8") as f:
            rewards = json.load(f)
            for reward in rewards[-50:]:
                time = datetime.fromisoformat(reward['given_at']).strftime('%Y-%m-%d %H:%M')
                currency_emoji = {"coins": "🪙", "stars": "⭐", "crystals": "💎"}.get(reward['currency'], "💰")
                logs.append({
                    "time": time,
                    "type": "currency",
                    "user_id": reward['user_id'],
                    "action": f"Выдача {currency_emoji} {reward['amount']}",
                    "details": f"Причина: {reward['reason']}"
                })
    except:
        pass
    
    # Логи рассылок
    try:
        with open("broadcasts.json", "r", encoding="utf-8") as f:
            broadcasts = json.load(f)
            for broadcast in broadcasts[-20:]:
                time = datetime.fromisoformat(broadcast['created_at']).strftime('%Y-%m-%d %H:%M')
                logs.append({
                    "time": time,
                    "type": "broadcast",
                    "user_id": "-",
                    "action": "Рассылка",
                    "details": f"Получатели: {broadcast['recipients']}"
                })
    except:
        pass
    
    # Сортируем по времени (свежие сверху)
    logs.sort(key=lambda x: x['time'], reverse=True)
    
    # Фильтруем по типу
    if type and type != "all":
        logs = [log for log in logs if log['type'] == type]
    
    # Ограничиваем по дням
    if days > 0:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        logs = [log for log in logs if log['time'] >= cutoff[:10]]
    
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "page": "logs",
        "logs": logs[:100],
        "total_logs": len(logs),
        "current_type": type,
        "current_days": days,
        "open_support_tickets": open_support_tickets
    })

# ========== ПОДДЕРЖКА ==========

# Страница поддержки
@app.get("/support", response_class=HTMLResponse)
async def support_page(
    request: Request, 
    auth: str = Depends(verify_auth),
    view: str = Query("active"),
    user_id: int = Query(None),
    ticket_id: int = Query(None)
):
    conn = sqlite3.connect('redpulse.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Статистика поддержки
    cursor.execute("SELECT COUNT(*) FROM support_tickets")
    total_support_tickets = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE status IN ('open', 'in_progress', 'waiting_admin')")
    open_support_tickets = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE status = 'closed'")
    closed_support_tickets = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE status = 'waiting_user'")
    waiting_user_support_tickets = cursor.fetchone()[0] or 0
    
    # Получаем чаты в зависимости от view
    support_chats = []
    
    if view == "active":
        cursor.execute("""
            SELECT 
                st.id as ticket_id,
                st.user_id,
                st.status,
                st.ticket_type,
                st.subject,
                st.created_at,
                st.last_activity,
                u.username,
                u.first_name,
                (SELECT message FROM support_messages WHERE ticket_id = st.id ORDER BY id DESC LIMIT 1) as last_message,
                (SELECT created_at FROM support_messages WHERE ticket_id = st.id ORDER BY id DESC LIMIT 1) as last_message_time,
                (SELECT COUNT(*) FROM support_messages WHERE ticket_id = st.id AND sender_type = 'user' AND is_read = 0) as unread
            FROM support_tickets st
            LEFT JOIN users u ON u.telegram_id = st.user_id
            WHERE st.status != 'closed'
            ORDER BY 
                CASE WHEN st.status = 'waiting_admin' THEN 1
                     WHEN st.status = 'waiting_user' THEN 2
                     WHEN st.status = 'in_progress' THEN 3
                     ELSE 4 END,
                st.last_activity DESC
        """)
        support_chats = cursor.fetchall()
    else:  # closed
        cursor.execute("""
            SELECT 
                st.id as ticket_id,
                st.user_id,
                st.status,
                st.ticket_type,
                st.subject,
                st.created_at,
                st.closed_at,
                u.username,
                u.first_name,
                (SELECT message FROM support_messages WHERE ticket_id = st.id ORDER BY id DESC LIMIT 1) as last_message
            FROM support_tickets st
            LEFT JOIN users u ON u.telegram_id = st.user_id
            WHERE st.status = 'closed'
            ORDER BY st.closed_at DESC
            LIMIT 50
        """)
        support_chats = cursor.fetchall()
    
    conn.close()
    
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "page": "support",
        "total_support_tickets": total_support_tickets,
        "open_support_tickets": open_support_tickets,
        "closed_support_tickets": closed_support_tickets,
        "waiting_user_support_tickets": waiting_user_support_tickets,
        "support_chats": support_chats,
        "current_view": view,
        "selected_user": user_id,
        "selected_ticket": ticket_id
    })

# API для получения сообщений
@app.get("/api/support/messages/{user_id}")
async def get_support_messages(user_id: int, auth: str = Depends(verify_auth)):
    conn = sqlite3.connect('redpulse.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id FROM support_tickets 
        WHERE user_id = ? AND status != 'closed'
        ORDER BY id DESC LIMIT 1
    """, (user_id,))
    
    ticket = cursor.fetchone()
    
    if not ticket:
        conn.close()
        return JSONResponse([])
    
    ticket_id = ticket['id']
    
    cursor.execute("""
        UPDATE support_messages 
        SET is_read = 1 
        WHERE ticket_id = ? AND sender_type = 'user'
    """, (ticket_id,))
    conn.commit()
    
    cursor.execute("""
        SELECT 
            sm.*,
            u.username,
            u.first_name
        FROM support_messages sm
        LEFT JOIN users u ON u.telegram_id = sm.user_id
        WHERE sm.ticket_id = ?
        ORDER BY sm.created_at ASC
    """, (ticket_id,))
    
    messages = cursor.fetchall()
    conn.close()
    
    result = []
    for msg in messages:
        sender_name = "Поддержка" if msg['sender_type'] == 'admin' else (msg['first_name'] or f"User{msg['user_id']}")
        result.append({
            "id": msg['id'],
            "user_id": msg['user_id'],
            "sender_type": msg['sender_type'],
            "sender_name": sender_name,
            "text": msg['message'],
            "time": msg['created_at'][:16] if msg['created_at'] else "",
            "status": "Прочитано" if msg['is_read'] else "Доставлено"
        })
    
    return JSONResponse(result)

# API для получения сообщений конкретного тикета
@app.get("/api/support/ticket/{ticket_id}/messages")
async def get_ticket_messages(ticket_id: int, auth: str = Depends(verify_auth)):
    conn = sqlite3.connect('redpulse.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            sm.*,
            u.username,
            u.first_name
        FROM support_messages sm
        LEFT JOIN users u ON u.telegram_id = sm.user_id
        WHERE sm.ticket_id = ?
        ORDER BY sm.created_at ASC
    """, (ticket_id,))
    
    messages = cursor.fetchall()
    conn.close()
    
    result = []
    for msg in messages:
        sender_name = "Поддержка" if msg['sender_type'] == 'admin' else (msg['first_name'] or f"User{msg['user_id']}")
        result.append({
            "id": msg['id'],
            "user_id": msg['user_id'],
            "sender_type": msg['sender_type'],
            "sender_name": sender_name,
            "text": msg['message'],
            "time": msg['created_at'][:16] if msg['created_at'] else "",
            "is_read": msg['is_read']
        })
    
    return JSONResponse(result)

# API для отправки сообщения
@app.post("/api/support/send")
async def send_support_message(
    request: Request,
    auth: str = Depends(verify_auth),
    _: None = Depends(support_send_rate_limit),
):
    global bot
    data = await request.json()
    user_id = data.get("user_id")
    message = (data.get("message") or "").strip()
    ticket_id = data.get("ticket_id")
    
    print(f"📨 Получен запрос на отправку пользователю {user_id}: {message[:30]}...")
    
    if not user_id or not message:
        return JSONResponse({"success": False, "error": "Не хватает данных"})
    if len(message) > 4096:
        return JSONResponse({"success": False, "error": "Сообщение слишком длинное"})
    
    conn = sqlite3.connect('redpulse.db')
    cursor = conn.cursor()
    
    final_ticket_id = ticket_id
    
    if ticket_id:
        cursor.execute("SELECT id, status FROM support_tickets WHERE id = ?", (ticket_id,))
        ticket = cursor.fetchone()
        
        if not ticket:
            conn.close()
            return JSONResponse({"success": False, "error": "Тикет не найден"})
        
        cursor.execute("""
            UPDATE support_tickets 
            SET status = 'waiting_user', last_activity = datetime('now')
            WHERE id = ?
        """, (ticket_id,))
    else:
        cursor.execute("""
            SELECT id FROM support_tickets 
            WHERE user_id = ? AND status != 'closed'
            ORDER BY id DESC LIMIT 1
        """, (user_id,))
        
        ticket = cursor.fetchone()
        
        if ticket:
            final_ticket_id = ticket[0]
            cursor.execute("""
                UPDATE support_tickets 
                SET status = 'waiting_user', last_activity = datetime('now')
                WHERE id = ?
            """, (final_ticket_id,))
        else:
            cursor.execute("""
                INSERT INTO support_tickets (user_id, status, subject, created_at, last_activity)
                VALUES (?, 'waiting_user', 'Обращение от админа', datetime('now'), datetime('now'))
            """, (user_id,))
            final_ticket_id = cursor.lastrowid
    
    cursor.execute("""
        INSERT INTO support_messages (ticket_id, user_id, sender_type, message, created_at)
        VALUES (?, ?, 'admin', ?, datetime('now'))
    """, (final_ticket_id, user_id, message))
    
    conn.commit()
    conn.close()
    
    if bot:
        try:
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            builder = InlineKeyboardBuilder()
            builder.button(text="✏️ Ответить", callback_data=f"support_reply_{final_ticket_id}")
            builder.button(text="📋 История", callback_data=f"support_ticket_{final_ticket_id}")
            builder.button(text="✅ Закрыть тикет", callback_data=f"support_close_{final_ticket_id}")
            builder.adjust(1)
            
            add_to_queue(
                user_id,
                f"📬 **Новый ответ от поддержки**\n\n{message}\n\n_Тикет #{final_ticket_id}_",
                "Markdown",
                builder.as_markup()
            )
            
            print(f"✅ Сообщение добавлено в очередь для пользователя {user_id}")
        except Exception as e:
            print(f"❌ Ошибка добавления в очередь: {e}")
    
    return JSONResponse({
        "success": True, 
        "ticket_id": final_ticket_id
    })

# ЗАКРЫТИЕ ТИКЕТА АДМИНОМ
@app.post("/api/support/close/{ticket_id}")
async def close_support_ticket(ticket_id: int, auth: str = Depends(verify_auth)):
    global bot
    print(f"🔒 Попытка закрыть тикет {ticket_id}")
    
    conn = sqlite3.connect('redpulse.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT user_id, status FROM support_tickets WHERE id = ?", (ticket_id,))
    ticket = cursor.fetchone()
    
    if not ticket:
        conn.close()
        print(f"❌ Тикет {ticket_id} не найден")
        return JSONResponse({"success": False, "error": "Тикет не найден"})
    
    user_id, current_status = ticket
    
    if current_status == 'closed':
        conn.close()
        print(f"❌ Тикет {ticket_id} уже закрыт")
        return JSONResponse({"success": False, "error": "Тикет уже закрыт"})
    
    cursor.execute("""
        UPDATE support_tickets 
        SET status = 'closed', closed_at = datetime('now'), closed_by = 'admin'
        WHERE id = ?
    """, (ticket_id,))
    
    conn.commit()
    conn.close()
    
    if bot and user_id:
        try:
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            builder = InlineKeyboardBuilder()
            builder.button(text="📋 Мои обращения", callback_data="support_my_tickets")
            
            add_to_queue(
                user_id,
                f"✅ **Тикет #{ticket_id} закрыт администратором**\n\n"
                f"Если у вас остались вопросы, создайте новое обращение через /support",
                "Markdown",
                builder.as_markup()
            )
            
            print(f"[OK] Уведомление о закрытии добавлено в очередь для пользователя {user_id}")
        except Exception as e:
            print(f"[ERR] Ошибка добавления в очередь: {e}")
    
    return JSONResponse({"success": True})

# ========== ФУНКЦИИ ДЛЯ ЗАПУСКА ==========

def init_bot(bot_instance):
    """Инициализация бота для отправки уведомлений"""
    global bot, bot_loop
    bot = bot_instance
    bot_loop = asyncio.get_event_loop()
    print("[OK] Бот инициализирован в админке")
    
    asyncio.run_coroutine_threadsafe(_process_queue(), bot_loop)
    print("[OK] Обработчик очереди запущен в цикле бота")

def start_admin():
    """Запуск админки в отдельном потоке"""
    thread = Thread(target=run_admin, daemon=True)
    thread.start()
    print("[OK] Админка запущена в фоновом потоке")

def run_admin():
    """Запуск FastAPI сервера"""
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")