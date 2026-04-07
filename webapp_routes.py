from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
import sqlite3
from pathlib import Path
from datetime import datetime
import random
import json
import os
import aiohttp
from core.progression import progress_for_xp

router = APIRouter()
WEBAPP_DIR = Path(__file__).parent / "webapp"

# Версия кэша - увеличивайте при изменениях в JS/CSS
CACHE_VERSION = "0.1.7"

def get_bot_token():
    """Получить токен бота (загружается при каждом вызове)"""
    from dotenv import load_dotenv
    load_dotenv()
    return os.getenv("BOT_TOKEN", "")

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def get_db():
    conn = sqlite3.connect('redpulse.db')
    conn.row_factory = sqlite3.Row
    return conn

def to_int(v, default=0):
    try:
        if v is None:
            return default
        i = int(float(v))
        return i if i >= 0 else default
    except Exception:
        return default

# ========== МАРШРУТЫ ==========
@router.get("/webapp", response_class=HTMLResponse)
async def get_webapp():
    """Отдаёт index.html с заголовками для отключения кэширования и версией"""
    from fastapi.responses import FileResponse
    response = FileResponse(WEBAPP_DIR / "index.html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["X-Cache-Version"] = CACHE_VERSION
    return response

@router.get("/webapp/version")
async def get_cache_version():
    """Возвращает текущую версию кэша для проверки обновлений"""
    return {"version": CACHE_VERSION, "timestamp": datetime.now().isoformat()}

@router.get("/sw.js")
async def get_service_worker():
    """Отдаёт Service Worker с заголовками без кэширования"""
    from fastapi.responses import FileResponse
    response = FileResponse(WEBAPP_DIR / "sw.js")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@router.get("/api/user/{user_id}")
async def get_user_data(user_id: int):
    """Получение данных пользователя с логированием и проверкой регистрации"""
    print(f'========== [API] ЗАПРОС /api/user/{user_id} ==========')
    conn = get_db()
    cursor = conn.cursor()

    try:
        # Проверяем, существует ли пользователь
        cursor.execute("SELECT telegram_id, first_name, username FROM users WHERE telegram_id = ?", (user_id,))
        user = cursor.fetchone()

        if not user:
            print(f'[API] userId={user_id} НЕ НАЙДЕН В БД!')
            conn.close()
            return {
                "error": "NOT_REGISTERED",
                "message": "Пользователь не найден. Нажмите /start в боте для регистрации."
            }, 403

        print(f'[API] userId={user_id} НАЙДЕН, загружаем данные...')
    except Exception as e:
        print(f"[API] Ошибка проверки пользователя: {e}")
        user = None

    conn.close()

    if user:
        # Загружаем полные данные пользователя
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT click_coins, stars, crystals, total_clicks,
                   click_power, auto_clicker, energy_multiplier,
                   xp, level, streak_days, referrals_count, tasks_completed,
                   first_name, username, created_at, first_play
            FROM users WHERE telegram_id = ?
        """, (user_id,))
        full_user = cursor.fetchone()
        conn.close()

        if full_user:
            def get(k, default=0):
                v = full_user[k]
                return default if v is None else v

            xp = int(get("xp", 0) or 0)
            p = progress_for_xp(xp)

            result = {
                "click_coins": get("click_coins", 0),
                "stars": get("stars", 0),
                "crystals": get("crystals", 0),
                "total_clicks": get("total_clicks", 0),
                "click_power": get("click_power", 1),
                "auto_clicker": bool(get("auto_clicker")),
                "max_energy": 1000 * (get("energy_multiplier") or 1),
                "energy": 1000 * (get("energy_multiplier") or 1),
                "xp": xp,
                "level": p["level"],
                "first_name": get("first_name", ""),
                "username": get("username", ""),
                "created_at": get("created_at", ""),
                "streak_days": get("streak_days", 0),
                "referrals_count": get("referrals_count", 0),
                "tasks_completed": get("tasks_completed", 0),
                "first_play": bool(get("first_play", True)) if get("first_play") is not None else True
            }
            print(f'[API] ОТВЕТ: click_coins={result["click_coins"]}, stars={result["stars"]}, crystals={result["crystals"]}')
            return result

    print(f'[API] full_user не найден для userId={user_id}')
    return {
        "error": "NOT_REGISTERED",
        "message": "Пользователь не найден. Нажмите /start в боте для регистрации."
    }, 403


@router.get("/api/debug/{user_id}")
async def debug_user(user_id: int):
    """DEBUG: Показывает ВСЕ данные пользователя из БД"""
    conn = get_db()
    cursor = conn.cursor()

    try:
        # Получаем ВСЕ колонки
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            return {
                "error": "Пользователь не найден",
                "telegram_id": user_id,
                "БД": "redpulse.db"
            }
        
        # Преобразуем в dict
        user_dict = dict(user)
        
        # Получаем список колонок
        columns = [description[0] for description in cursor.description]
        
        return {
            "telegram_id": user_id,
            "найдено": True,
            "колонки": columns,
            "данные": user_dict,
            "farm_state_json": user_dict.get('farm_state_json'),
            "кратко": {
                "click_coins": user_dict.get('click_coins'),
                "stars": user_dict.get('stars'),
                "crystals": user_dict.get('crystals'),
                "level": user_dict.get('level'),
                "xp": user_dict.get('xp'),
                "temp": user_dict.get('temp'),
                "max_temp": user_dict.get('max_temp'),
                "reactor_level": user_dict.get('reactor_level'),
                "blocks_placed": user_dict.get('blocks_placed'),
                "reactions_triggered": user_dict.get('reactions_triggered')
            }
        }
    except Exception as e:
        return {"error": str(e), "telegram_id": user_id}
    finally:
        conn.close()

@router.post("/api/save-clicks")
async def save_clicks(request: Request):
    """Сохраняет валюту и данные из фермы в БД"""
    data = await request.json()
    user_id = data.get("userId")

    click_coins = to_int(data.get("click_coins"), 0)
    stars = to_int(data.get("stars"), 0)
    crystals = to_int(data.get("crystals"), 0)
    total_clicks_in = to_int(data.get("total_clicks"), 0)
    click_power = max(1, to_int(data.get("click_power", 1), 1))
    auto_clicker = data.get("auto_clicker", False)
    max_energy = max(1000, to_int(data.get("max_energy", 1000), 1000))
    energy_multiplier = max(1, max_energy // 1000)

    conn = get_db()
    cursor = conn.cursor()

    old_total_clicks = 0
    old_xp = 0
    old_coins = 0
    old_stars = 0
    old_crystals = 0
    try:
        cursor.execute("SELECT total_clicks, xp, click_coins, stars, crystals FROM users WHERE telegram_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            old_total_clicks = int(row["total_clicks"] or 0)
            old_xp = int(row["xp"] or 0)
            old_coins = int(row["click_coins"] or 0)
            old_stars = int(row["stars"] or 0)
            old_crystals = int(row["crystals"] or 0)
    except Exception as e:
        print(f"Error fetching old data: {e}")

    # Берём БОЛЬШЕЕ значение из БД и от фермы (чтобы не потерять данные)
    total_clicks = max(old_total_clicks, total_clicks_in)
    final_coins = max(old_coins, click_coins)
    final_stars = max(old_stars, stars)
    final_crystals = max(old_crystals, crystals)
    
    delta_clicks = max(0, total_clicks - old_total_clicks)
    xp_gain = delta_clicks * 10  # 1 клик = 10 XP

    # Бонус общей казны
    try:
        cursor.execute("SELECT bonus_active_until FROM global_bank WHERE id = 1")
        row = cursor.fetchone()
        if row and row[0]:
            try:
                until = datetime.fromisoformat(str(row[0]).replace("T", " ")[:19])
                if until > datetime.now():
                    xp_gain *= 2
            except Exception:
                pass
    except Exception:
        pass

    xp = old_xp + xp_gain
    p = progress_for_xp(xp)
    level = p["level"]

    # Общая казна
    try:
        cursor.execute("INSERT OR IGNORE INTO global_bank(id, coins, xp, level, target) VALUES(1, 0, 0, 1, 100000)")
        add_bank = min(5000, delta_clicks)
        if add_bank > 0:
            cursor.execute("UPDATE global_bank SET coins = coins + ?, xp = xp + ? WHERE id = 1", (add_bank, add_bank))
    except Exception:
        pass

    try:
        cursor.execute("""
            UPDATE users SET click_coins = ?, stars = ?, crystals = ?, total_clicks = ?,
                click_power = ?, auto_clicker = ?, energy_multiplier = ?,
                xp = ?, level = ?, last_activity = CURRENT_TIMESTAMP
            WHERE telegram_id = ?
        """, (final_coins, final_stars, final_crystals, total_clicks, click_power, auto_clicker, energy_multiplier, xp, level, user_id))
    except Exception as e:
        print(f"Error updating user: {e}")

    conn.commit()
    conn.close()
    return {"status": "ok", "xp": xp, "level": level, "click_coins": final_coins, "stars": final_stars, "crystals": final_crystals}

@router.post("/api/buy-boost")
async def buy_boost(request: Request):
    data = await request.json()
    user_id = data.get("userId")
    boost_type = data.get("type")
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT click_coins, click_power, auto_clicker, energy_multiplier FROM users WHERE telegram_id = ?", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return {"success": False, "error": "User not found"}
    
    prices = {
        "energy": 800 * (1.55 ** ((user[3] or 1) - 1)),
        "power": 500 * (1.5 ** ((user[2] or 1) - 1)),
        "auto": 2000
    }
    
    price = int(prices.get(boost_type, 0))
    if user[0] < price:
        conn.close()
        return {"success": False, "error": "Not enough coins"}
    
    if boost_type == "energy":
        cursor.execute("UPDATE users SET click_coins = click_coins - ?, energy_multiplier = energy_multiplier + 1 WHERE telegram_id = ?", (price, user_id))
    elif boost_type == "power":
        cursor.execute("UPDATE users SET click_coins = click_coins - ?, click_power = click_power + 1 WHERE telegram_id = ?", (price, user_id))
    elif boost_type == "auto":
        cursor.execute("UPDATE users SET click_coins = click_coins - ?, auto_clicker = 1 WHERE telegram_id = ?", (price, user_id))
    
    conn.commit()
    conn.close()
    return {"success": True}

@router.post("/api/exchange-to-crystals")
async def exchange_to_crystals(request: Request):
    data = await request.json()
    user_id = data.get("userId")
    amount = to_int(data.get("amount"), 100)
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT click_coins, crystals FROM users WHERE telegram_id = ?", (user_id,))
    user = cursor.fetchone()
    
    if user and user[0] >= amount:
        cursor.execute("UPDATE users SET click_coins = click_coins - ?, crystals = crystals + 1 WHERE telegram_id = ?", (amount, user_id))
        conn.commit()
        conn.close()
        return {"status": "ok"}
    
    conn.close()
    return {"status": "error", "message": "Not enough coins"}

@router.get("/api/profile/{user_id}")
async def get_profile(user_id: int):
    conn = get_db()
    cursor = conn.cursor()

    try:
        # Получаем данные пользователя
        cursor.execute("""
            SELECT first_name, username, level, total_clicks, tasks_completed,
                   streak_days, click_power, referrals_count, created_at,
                   reactor_level, blocks_placed, reactions_triggered,
                   click_coins, stars, crystals
            FROM users WHERE telegram_id = ?
        """, (user_id,))
        user = cursor.fetchone()

        # Получаем место в рейтинге
        cursor.execute("""
            SELECT telegram_id FROM users
            WHERE is_banned = 0
            ORDER BY stars DESC, total_clicks DESC
        """)
        all_users = cursor.fetchall()
        user_rank = next((i + 1 for i, u in enumerate(all_users) if u["telegram_id"] == user_id), 0)
    except Exception as e:
        print(f"Error fetching profile: {e}")
        user = None
        user_rank = 0

    conn.close()

    if user:
        reactions = int(user["reactions_triggered"] or 0)
        # Уровень игрока: каждые 200 реакций = +1 (медленнее, не сбрасывается)
        player_level = (reactions // 200) + 1

        return {
            "first_name": user["first_name"] or "Игрок",
            "username": user["username"],
            "level": player_level,
            "total_clicks": user["total_clicks"] or 0,
            "tasks_completed": user["tasks_completed"] or 0,
            "streak_days": user["streak_days"] or 0,
            "click_power": user["click_power"] or 1,
            "referrals_count": user["referrals_count"] or 0,
            "created_at": user["created_at"] or "",
            "core_level": user["reactor_level"] or 1,
            "blocks_placed": user["blocks_placed"] or 0,
            "reactions_triggered": reactions,
            "click_coins": user["click_coins"] or 0,
            "stars": user["stars"] or 0,
            "crystals": user["crystals"] or 0,
            "rating_rank": user_rank
        }
    return {}

@router.post("/api/save-farm-stats")
async def save_farm_stats(request: Request):
    """Сохраняет статистику фермы (реактора) и валюту в БД"""
    data = await request.json()
    user_id = data.get("userId")

    reactor_level = max(1, int(data.get("reactor_level", 1)))
    blocks_placed = int(data.get("blocks_placed", 0))
    reactions_triggered = int(data.get("reactions_triggered", 0))
    total_energy_produced = int(data.get("total_energy_produced", 0))

    # Валюта из фермы (основной баланс)
    click_coins = int(data.get("click_coins", 0))
    stars = int(data.get("stars", 0))
    crystals = int(data.get("crystals", 0))

    # Банк фермы (виртуальный)
    bank_coins = int(data.get("bank_coins", 0))
    bank_stars = int(data.get("bank_stars", 0))
    bank_crystals = int(data.get("bank_crystals", 0))

    print(f'[save-farm-stats] userId={user_id}, банк={bank_coins}🪙/{bank_stars}⭐/{bank_crystals}💎, монеты={click_coins}')

    conn = get_db()
    cursor = conn.cursor()

    try:
        # Получаем текущие значения из БД
        cursor.execute("SELECT click_coins, stars, crystals, bank_coins, bank_stars, bank_crystals, reactions_triggered, blocks_placed, reactor_level, total_energy_produced FROM users WHERE telegram_id = ?", (user_id,))
        row = cursor.fetchone()

        if row:
            # Берём БОЛЬШЕЕ значение для валюты (чтобы не потерять данные)
            db_coins = int(row["click_coins"] or 0)
            db_stars = int(row["stars"] or 0)
            db_crystals = int(row["crystals"] or 0)
            db_bank_coins = int(row["bank_coins"] or 0)
            db_bank_stars = int(row["bank_stars"] or 0)
            db_bank_crystals = int(row["bank_crystals"] or 0)
            db_reactions = int(row["reactions_triggered"] or 0)
            db_blocks = int(row["blocks_placed"] or 0)
            db_reactor = int(row["reactor_level"] or 1)
            db_energy = int(row["total_energy_produced"] or 0)

            final_coins = max(db_coins, click_coins)
            final_stars = max(db_stars, stars)
            final_crystals = max(db_crystals, crystals)
            final_bank_coins = max(db_bank_coins, bank_coins)
            final_bank_stars = max(db_bank_stars, bank_stars)
            final_bank_crystals = max(db_bank_crystals, bank_crystals)
            # ВАЖНО: для статистики тоже берём максимум (чтобы не сбросить прогресс)
            final_reactions = max(db_reactions, reactions_triggered)
            final_blocks = max(db_blocks, blocks_placed)
            final_reactor = max(db_reactor, reactor_level)
            final_energy = max(db_energy, total_energy_produced)

            print(f'[save-farm-stats] БД: было реакции={db_reactions}, стало={final_reactions}')
        else:
            final_coins = click_coins
            final_stars = stars
            final_crystals = crystals
            final_bank_coins = bank_coins
            final_bank_stars = bank_stars
            final_bank_crystals = bank_crystals
            final_reactions = reactions_triggered
            final_blocks = blocks_placed
            final_reactor = reactor_level
            final_energy = total_energy_produced
            print(f'[save-farm-stats] Пользователь не найден, создаём новые значения')

        cursor.execute("""
            UPDATE users SET
                reactor_level = ?,
                blocks_placed = ?,
                reactions_triggered = ?,
                total_energy_produced = ?,
                click_coins = ?,
                stars = ?,
                crystals = ?,
                bank_coins = ?,
                bank_stars = ?,
                bank_crystals = ?,
                first_play = 0,
                last_activity = CURRENT_TIMESTAMP
            WHERE telegram_id = ?
        """, (final_reactor, final_blocks, final_reactions, final_energy,
              final_coins, final_stars, final_crystals,
              final_bank_coins, final_bank_stars, final_bank_crystals,
              user_id))
        conn.commit()
        conn.close()
        print(f'[save-farm-stats] ✅ Успешно сохранено в БД')
        return {"status": "ok", "click_coins": final_coins, "stars": final_stars, "crystals": final_crystals, "bank_coins": final_bank_coins}
    except Exception as e:
        print(f"[save-farm-stats] ❌ Ошибка: {e}")
        conn.close()
        return {"status": "error", "message": str(e)}


@router.get("/api/farm-stats/{user_id}")
async def get_farm_stats(user_id: int):
    """Загружает статистику фермы из БД"""
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT reactor_level, blocks_placed, reactions_triggered, total_energy_produced
            FROM users WHERE telegram_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "reactor_level": row["reactor_level"] or 1,
                "blocks_placed": row["blocks_placed"] or 0,
                "reactions_triggered": row["reactions_triggered"] or 0,
                "total_energy_produced": row["total_energy_produced"] or 0
            }

    except Exception as e:
        print(f"Error fetching farm stats: {e}")

    conn.close()
    return {}


@router.get("/api/farm-state/{user_id}")
async def get_farm_state(user_id: int):
    """Загружает полное состояние фермы из БД"""
    print(f'========== [API] ЗАПРОС /api/farm-state/{user_id} ==========')
    conn = get_db()
    cursor = conn.cursor()

    try:
        print(f'[get_farm_state] Запрос для userId={user_id}')
        cursor.execute("""
            SELECT farm_state_json, reactor_level, blocks_placed, reactions_triggered,
                   temp, max_temp, level, xp, click_coins, stars, crystals,
                   bank_coins, bank_stars, bank_crystals, first_play
            FROM users WHERE telegram_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            result = {
                "reactor_level": row["reactor_level"] or 1,
                "blocks_placed": row["blocks_placed"] or 0,
                "reactions_triggered": row["reactions_triggered"] or 0,
                "temp": row["temp"] or 0,
                "maxTemp": row["max_temp"] or 100,
                "level": row["level"] or 1,
                "xp": row["xp"] or 0,
                "coins": row["click_coins"] or 0,
                "stars": row["stars"] or 0,
                "crystals": row["crystals"] or 0,
                "bankCoins": row["bank_coins"] or 0,
                "bankCrystals": row["bank_crystals"] or 0,
                "bankStars": row["bank_stars"] or 0,
                "firstPlay": bool(row["first_play"]) if row["first_play"] is not None else True
            }

            # Если есть farm_state_json, объединяем
            if row["farm_state_json"]:
                import json
                farm_state = json.loads(row["farm_state_json"])
                # Добавляем lastTapTime из farm_state_json
                if 'lastTapTime' in farm_state:
                    result['lastTapTime'] = farm_state['lastTapTime']
                result = { **result, **farm_state }

            print(f'[get_farm_state] userId={user_id}, данные:', result)
            return result
        else:
            print(f'[get_farm_state] userId={user_id}, данных нет в БД')

    except Exception as e:
        print(f"Error fetching farm state: {e}")

    conn.close()
    return {}


@router.post("/api/save-farm-state")
async def save_farm_state(request: Request):
    """Сохраняет полное состояние фермы в БД"""
    data = await request.json()
    user_id = data.get("userId")
    farm_state = data.get("farmState", {})

    conn = get_db()
    cursor = conn.cursor()

    try:
        import json
        
        # Получаем текущие значения из БД
        cursor.execute("""
            SELECT blocks_placed, reactions_triggered, reactor_level, total_energy_produced,
                   click_coins, stars, crystals, bank_coins, bank_stars, bank_crystals,
                   level, xp, temp, max_temp, first_play
            FROM users WHERE telegram_id = ?
        """, (user_id,))
        db_row = cursor.fetchone()
        
        # Значения из запроса
        req_blocks = farm_state.get('blocks_placed', 0)
        req_reactions = farm_state.get('reactions_triggered', 0)
        req_reactor = farm_state.get('reactor_level', 1)
        req_energy = farm_state.get('total_energy_produced', 0)
        req_coins = farm_state.get('coins', 0)
        req_stars = farm_state.get('stars', 0)
        req_crystals = farm_state.get('crystals', 0)
        req_bank_coins = farm_state.get('bankCoins', 0)
        req_bank_stars = farm_state.get('bankStars', 0)
        req_bank_crystals = farm_state.get('bankCrystals', 0)
        req_level = farm_state.get('level', 1)
        req_xp = farm_state.get('xp', 0)
        req_temp = farm_state.get('temp', 0)
        req_max_temp = farm_state.get('maxTemp', 100)
        
        if db_row:
            # Берём МАКСИМУМ для статистики (реакции, блоки, энергия)
            final_blocks = max(int(db_row["blocks_placed"] or 0), req_blocks)
            final_reactions = max(int(db_row["reactions_triggered"] or 0), req_reactions)
            final_reactor = max(int(db_row["reactor_level"] or 1), req_reactor)
            final_energy = max(int(db_row["total_energy_produced"] or 0), req_energy)
            # ВАЖНО: для валюты берём значение из запроса напрямую (НЕ max!)
            # чтобы потраченные монеты не перезаписывались старым значением из БД
            final_coins = req_coins
            final_stars = req_stars
            final_crystals = req_crystals
            final_bank_coins = req_bank_coins
            final_bank_stars = req_bank_stars
            final_bank_crystals = req_bank_crystals
            # XP: берём максимум, затем ПЕРЕСЧИТЫВАЕМ уровень из XP
            final_xp = max(int(db_row["xp"] or 0), req_xp)
            final_level = progress_for_xp(final_xp)["level"]
            final_temp = int(db_row["temp"] or 0) if req_temp == 0 else req_temp
            final_max_temp = int(db_row["max_temp"] or 100) if req_max_temp == 100 else req_max_temp
            # first_play: если в запросе False, сохраняем 0
            final_first_play = 0 if farm_state.get('firstPlay') is False else (int(db_row["first_play"]) if db_row["first_play"] is not None else 1)
            # lastTapTime сохраняем из запроса
            import time
            final_last_tap_time = farm_state.get('lastTapTime', int(time.time() * 1000))

            print(f'[save-farm-state] max(): реакции {db_row["reactions_triggered"]} -> {final_reactions}, блоки {db_row["blocks_placed"]} -> {final_blocks}')
        else:
            # Нет данных в БД - используем значения из запроса
            import time
            final_blocks = req_blocks
            final_reactions = req_reactions
            final_reactor = req_reactor
            final_energy = req_energy
            final_coins = req_coins
            final_stars = req_stars
            final_crystals = req_crystals
            final_bank_coins = req_bank_coins
            final_bank_stars = req_bank_stars
            final_bank_crystals = req_bank_crystals
            final_xp = req_xp
            final_level = progress_for_xp(final_xp)["level"]
            final_temp = req_temp
            final_max_temp = req_max_temp
            final_first_play = 0 if farm_state.get('firstPlay') is False else 1
            final_last_tap_time = farm_state.get('lastTapTime', int(time.time() * 1000))

        cursor.execute("""
            UPDATE users SET
                farm_state_json = ?,
                blocks_placed = ?,
                reactions_triggered = ?,
                reactor_level = ?,
                total_energy_produced = ?,
                click_coins = ?,
                stars = ?,
                crystals = ?,
                bank_coins = ?,
                bank_stars = ?,
                bank_crystals = ?,
                level = ?,
                xp = ?,
                temp = ?,
                max_temp = ?,
                first_play = ?,
                last_activity = CURRENT_TIMESTAMP
            WHERE telegram_id = ?
        """, (
            json.dumps(farm_state),
            final_blocks,
            final_reactions,
            final_reactor,
            final_energy,
            final_coins,
            final_stars,
            final_crystals,
            final_bank_coins,
            final_bank_stars,
            final_bank_crystals,
            final_level,
            final_xp,
            final_temp,
            final_max_temp,
            final_first_play,
            user_id
        ))
        print(f'[save-farm-state] ✅ Сохранено: реакции={final_reactions}, блоки={final_blocks}, монеты={final_coins}')
        conn.commit()
        conn.close()
        return {"status": "ok"}
    except Exception as e:
        print(f"Error saving farm state: {e}")
        conn.close()
        return {"status": "error", "message": str(e)}

@router.get("/api/tasks/{user_id}")
async def get_tasks(user_id: int):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, title, reward_coins, reward_stars, task_type FROM tasks WHERE is_active = 1")
    all_tasks = cursor.fetchall()
    
    completed = set()
    try:
        cursor.execute("SELECT task_id FROM user_tasks WHERE user_id = ?", (user_id,))
        for row in cursor.fetchall():
            completed.add(row[0])
    except Exception:
        pass
    
    conn.close()
    
    tasks = []
    for t in all_tasks:
        tasks.append({
            "id": t["id"],
            "title": t["title"],
            "reward_coins": t["reward_coins"] or 0,
            "reward_stars": t["reward_stars"] or 0,
            "completed": t["id"] in completed
        })
    
    return tasks

@router.post("/api/complete-task")
async def complete_task(request: Request):
    data = await request.json()
    user_id = data.get("userId")
    task_id = data.get("taskId")
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if already completed
    cursor.execute("SELECT id FROM user_tasks WHERE user_id = ? AND task_id = ?", (user_id, task_id))
    if cursor.fetchone():
        conn.close()
        return {"success": False, "error": "Already completed"}
    
    # Get task
    cursor.execute("SELECT reward_coins, reward_stars FROM tasks WHERE id = ?", (task_id,))
    task = cursor.fetchone()
    
    if not task:
        conn.close()
        return {"success": False, "error": "Task not found"}
    
    # Add completion record
    cursor.execute("INSERT INTO user_tasks (user_id, task_id) VALUES (?, ?)", (user_id, task_id))
    
    # Give rewards
    cursor.execute("""
        UPDATE users SET 
            click_coins = click_coins + ?,
            stars = stars + ?,
            tasks_completed = tasks_completed + 1
        WHERE telegram_id = ?
    """, (task["reward_coins"], task["reward_stars"], user_id))
    
    conn.commit()
    conn.close()
    
    return {"success": True, "reward_coins": task["reward_coins"], "reward_stars": task["reward_stars"]}

@router.get("/api/rating")
async def get_rating():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT telegram_id, first_name, username, stars
        FROM users
        WHERE is_banned = 0
        ORDER BY stars DESC
        LIMIT 20
    """)
    users = cursor.fetchall()
    conn.close()
    
    return [{
        "telegram_id": u["telegram_id"],
        "first_name": u["first_name"] or "Игрок",
        "username": u["username"] or "unknown",
        "stars": u["stars"] or 0
    } for u in users]

@router.get("/api/avatar/{user_id}")
async def get_avatar(user_id: int):
    """Получить URL аватара пользователя через Telegram Bot API"""
    bot_token = get_bot_token()
    if not bot_token:
        return {"url": ""}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.telegram.org/bot{bot_token}/getUserProfilePhotos?user_id={user_id}&limit=1") as resp:
                data = await resp.json()
                if data.get("ok") and data["result"]["total_count"] > 0:
                    file_id = data["result"]["photos"][0][-1]["file_id"]
                    async with session.get(f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}") as resp2:
                        file_data = await resp2.json()
                        if file_data.get("ok"):
                            file_path = file_data["result"]["file_path"]
                            url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
                            return {"url": url}
    except Exception as e:
        print(f"Avatar fetch error: {e}")

    return {"url": ""}

@router.get("/api/shop/{category}")
async def get_shop_items(category: str, userId: int = None):
    conn = get_db()
    cursor = conn.cursor()
    
    items = []
    
    if category == "cases":
        cursor.execute("SELECT id, name, price_coins, price_crystals FROM cases WHERE is_active = 1")
        cases = cursor.fetchall()
        
        user_cases = {}
        if userId:
            cursor.execute("""
                SELECT case_id, SUM(count) as total FROM user_cases 
                WHERE user_id = ? GROUP BY case_id
            """, (userId,))
            for row in cursor.fetchall():
                user_cases[row[0]] = row[1]
        
        for c in cases:
            price = f"{c['price_coins']} 🪙" if c['price_coins'] else f"{c['price_crystals']} 💎"
            items.append({
                "id": str(c["id"]),
                "name": c["name"],
                "price": price,
                "icon": "📦",
                "count": user_cases.get(c["id"], 0),
                "canBuy": True
            })
    
    elif category == "boosts":
        boosts = [
            {"id": "energy", "name": "Энергия +500", "price": "500 🪙", "icon": "🔋"},
            {"id": "power", "name": "Сила +1", "price": "300 🪙", "icon": "⚡"},
            {"id": "auto", "name": "Автокликер", "price": "1000 🪙", "icon": "🤖"}
        ]
        items = boosts
    
    elif category == "skins":
        skins = [
            {"id": "red", "name": "Красная тема", "price": "500 💎", "icon": "🎨"},
            {"id": "gold", "name": "Золотая рамка", "price": "300 💎", "icon": "👑"},
            {"id": "blue", "name": "Синяя тема", "price": "500 💎", "icon": "💙"}
        ]
        items = skins
    
    elif category == "avatars":
        avatars = [
            {"id": "avatar1", "name": "Космонавт", "price": "150 💎", "icon": "👨‍🚀"},
            {"id": "avatar2", "name": "Ниндзя", "price": "150 💎", "icon": "🥷"},
            {"id": "avatar3", "name": "Бизнесмен", "price": "150 💎", "icon": "👔"}
        ]
        items = avatars
    
    conn.close()
    return items

@router.post("/api/buy-shop-item")
async def buy_shop_item(request: Request):
    data = await request.json()
    user_id = data.get("userId")
    category = data.get("category")
    item_id = data.get("itemId")
    
    conn = get_db()
    cursor = conn.cursor()
    
    if category == "cases":
        try:
            case_id = int(item_id)
            cursor.execute("SELECT price_coins, price_crystals FROM cases WHERE id = ?", (case_id,))
            case = cursor.fetchone()
            
            if case:
                if case["price_coins"]:
                    cursor.execute("SELECT click_coins FROM users WHERE telegram_id = ?", (user_id,))
                    user = cursor.fetchone()
                    if user and user[0] >= case["price_coins"]:
                        cursor.execute("UPDATE users SET click_coins = click_coins - ? WHERE telegram_id = ?", (case["price_coins"], user_id))
                        cursor.execute("INSERT INTO user_cases (user_id, case_id, count) VALUES (?, ?, 1)", (user_id, case_id))
                        conn.commit()
                        conn.close()
                        return {"success": True}
                elif case["price_crystals"]:
                    cursor.execute("SELECT crystals FROM users WHERE telegram_id = ?", (user_id,))
                    user = cursor.fetchone()
                    if user and user[0] >= case["price_crystals"]:
                        cursor.execute("UPDATE users SET crystals = crystals - ? WHERE telegram_id = ?", (case["price_crystals"], user_id))
                        cursor.execute("INSERT INTO user_cases (user_id, case_id, count) VALUES (?, ?, 1)", (user_id, case_id))
                        conn.commit()
                        conn.close()
                        return {"success": True}
        except Exception as e:
            print(f"Error buying case: {e}")
    
    conn.close()
    return {"success": False, "error": "Purchase failed"}

# ========== КАЗИНО ==========
@router.post("/api/casino-dice")
async def casino_dice(request: Request):
    data = await request.json()
    user_id = data.get("userId")
    bet = to_int(data.get("bet"), 0)
    
    if bet < 10 or bet > 5000:
        return {"error": "Invalid bet"}
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT click_coins FROM users WHERE telegram_id = ?", (user_id,))
    user = cursor.fetchone()
    
    if not user or user[0] < bet:
        conn.close()
        return {"error": "Not enough coins"}
    
    # Roll dice (1-6)
    roll = random.randint(1, 6)
    win = roll >= 4
    win_amount = bet * 2 if win else 0
    
    if win:
        cursor.execute("UPDATE users SET click_coins = click_coins + ? WHERE telegram_id = ?", (win_amount - bet, user_id))
    else:
        cursor.execute("UPDATE users SET click_coins = click_coins - ? WHERE telegram_id = ?", (bet, user_id))
    
    conn.commit()
    conn.close()
    
    return {"roll": roll, "win": win, "winAmount": win_amount}

@router.post("/api/casino-slots")
async def casino_slots(request: Request):
    data = await request.json()
    user_id = data.get("userId")
    bet = to_int(data.get("bet"), 0)
    
    if bet < 10 or bet > 5000:
        return {"error": "Invalid bet"}
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT click_coins FROM users WHERE telegram_id = ?", (user_id,))
    user = cursor.fetchone()
    
    if not user or user[0] < bet:
        conn.close()
        return {"error": "Not enough coins"}
    
    # Spin slots
    reels = ["🍒", "🍋", "⭐", "💎"]
    weights = [55, 30, 12, 3]
    a, b, c = random.choices(reels, weights=weights, k=3)
    
    multiplier = 0
    if a == b == c == "💎":
        multiplier = 10
    elif a == b == c == "⭐":
        multiplier = 5
    elif a == b == c == "🍒":
        multiplier = 3
    elif (a == "🍒" and b == "🍒") or (b == "🍒" and c == "🍒") or (a == "🍒" and c == "🍒"):
        multiplier = 2
    
    win_amount = bet * multiplier if multiplier > 0 else 0
    
    if win_amount > 0:
        cursor.execute("UPDATE users SET click_coins = click_coins + ? WHERE telegram_id = ?", (win_amount - bet, user_id))
    else:
        cursor.execute("UPDATE users SET click_coins = click_coins - ? WHERE telegram_id = ?", (bet, user_id))
    
    conn.commit()
    conn.close()
    
    return {"reels": [a, b, c], "win": multiplier > 0, "multiplier": multiplier, "winAmount": win_amount}

@router.post("/api/casino-bj-start")
async def casino_bj_start(request: Request):
    data = await request.json()
    user_id = data.get("userId")
    bet = to_int(data.get("bet"), 0)
    
    if bet < 10 or bet > 5000:
        return {"error": "Invalid bet"}
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT click_coins FROM users WHERE telegram_id = ?", (user_id,))
    user = cursor.fetchone()
    
    if not user or user[0] < bet:
        conn.close()
        return {"error": "Not enough coins"}
    
    # Deduct bet
    cursor.execute("UPDATE users SET click_coins = click_coins - ? WHERE telegram_id = ?", (bet, user_id))
    conn.commit()
    conn.close()
    
    # Deal cards
    deck = [v for _ in range(4) for v in range(2, 15)]
    random.shuffle(deck)
    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]
    
    def card_str(v):
        if v == 14: return "A"
        if v == 13: return "K"
        if v == 12: return "Q"
        if v == 11: return "J"
        return str(v)
    
    def hand_value(hand):
        total = 0
        aces = 0
        for v in hand:
            if v == 14:
                aces += 1
                total += 11
            elif v >= 11:
                total += 10
            else:
                total += v
        while total > 21 and aces:
            total -= 10
            aces -= 1
        return total
    
    return {
        "player": [card_str(c) for c in player],
        "dealer": [card_str(dealer[0]), "?"],
        "playerValue": hand_value(player),
        "bet": bet,
        "deck": deck
    }

@router.post("/api/casino-bj-hit")
async def casino_bj_hit(request: Request):
    data = await request.json()
    user_id = data.get("userId")
    
    # Get game state from request (simplified - in production use session)
    deck = data.get("deck", [])
    player = data.get("player", [])
    bet = data.get("bet", 0)
    
    if not deck:
        deck = [v for _ in range(4) for v in range(2, 15)]
        random.shuffle(deck)
    
    # Convert back to int
    card_map = {"A": 14, "K": 13, "Q": 12, "J": 11}
    player_int = [card_map.get(c, int(c)) for c in player]
    player_int.append(deck.pop())
    
    def hand_value(hand):
        total = 0
        aces = 0
        for v in hand:
            if v == 14:
                aces += 1
                total += 11
            elif v >= 11:
                total += 10
            else:
                total += v
        while total > 21 and aces:
            total -= 10
            aces -= 1
        return total
    
    def card_str(v):
        if v == 14: return "A"
        if v == 13: return "K"
        if v == 12: return "Q"
        if v == 11: return "J"
        return str(v)
    
    value = hand_value(player_int)
    
    return {
        "player": [card_str(c) for c in player_int],
        "playerValue": value,
        "busted": value > 21,
        "deck": deck,
        "bet": bet
    }

@router.post("/api/casino-bj-stand")
async def casino_bj_stand(request: Request):
    data = await request.json()
    user_id = data.get("userId")
    player = data.get("player", [])
    dealer = data.get("dealer", [])
    deck = data.get("deck", [])
    bet = data.get("bet", 0)
    
    card_map = {"A": 14, "K": 13, "Q": 12, "J": 11}
    player_int = [card_map.get(c, int(c)) for c in player]
    dealer_int = [card_map.get(c, int(c)) for c in dealer]
    
    # Convert ? to actual card
    if dealer_int[1] == 0 or dealer[1] == "?":
        dealer_int[1] = deck.pop() if deck else random.randint(2, 14)
    
    def hand_value(hand):
        total = 0
        aces = 0
        for v in hand:
            if v == 14:
                aces += 1
                total += 11
            elif v >= 11:
                total += 10
            else:
                total += v
        while total > 21 and aces:
            total -= 10
            aces -= 1
        return total
    
    def card_str(v):
        if v == 14: return "A"
        if v == 13: return "K"
        if v == 12: return "Q"
        if v == 11: return "J"
        return str(v)
    
    # Dealer draws until 17
    while hand_value(dealer_int) < 17 and deck:
        dealer_int.append(deck.pop())
    
    player_value = hand_value(player_int)
    dealer_value = hand_value(dealer_int)
    
    win = False
    push = False
    win_amount = 0
    
    if dealer_value > 21 or player_value > dealer_value:
        win = True
        win_amount = bet * 2
    elif player_value == dealer_value:
        push = True
        win_amount = bet
    
    # Update user balance
    conn = get_db()
    cursor = conn.cursor()
    if win_amount > 0:
        cursor.execute("UPDATE users SET click_coins = click_coins + ? WHERE telegram_id = ?", (win_amount, user_id))
    conn.commit()
    conn.close()
    
    return {
        "player": [card_str(c) for c in player_int],
        "dealer": [card_str(c) for c in dealer_int],
        "playerValue": player_value,
        "dealerValue": dealer_value,
        "win": win,
        "push": push,
        "winAmount": win_amount
    }
