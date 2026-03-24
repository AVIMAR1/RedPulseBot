from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
import sqlite3
from pathlib import Path
from datetime import datetime
import random
import json
from core.progression import progress_for_xp

router = APIRouter()
WEBAPP_DIR = Path(__file__).parent / "webapp"

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
    return FileResponse(WEBAPP_DIR / "index.html")

@router.get("/webapp/test")
async def get_webapp_test():
    """Тестовая страница Mini App с фиксированным user_id для локальной разработки"""
    # Для локального тестирования без Telegram
    html = (WEBAPP_DIR / "index.html").read_text(encoding='utf-8')
    # Заменяем получение userId из Telegram на тестовый ID
    test_html = html.replace(
        'const userId = tg.initDataUnsafe?.user?.id;',
        'const userId = tg.initDataUnsafe?.user?.id || 123456789; // TEST MODE'
    )
    return HTMLResponse(content=test_html)

@router.get("/api/user/{user_id}")
async def get_user_data(user_id: int):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT click_coins, stars, crystals, total_clicks,
                   click_power, auto_clicker, energy_multiplier, theme,
                   xp, level, streak_days, referrals_count, tasks_completed,
                   first_name, username, created_at
            FROM users WHERE telegram_id = ?
        """, (user_id,))
        user = cursor.fetchone()
    except Exception as e:
        print(f"Error fetching user: {e}")
        user = None
    
    conn.close()
    
    if user:
        def get(k, default=0):
            v = user[k]
            return default if v is None else v
        
        xp = int(get("xp", 0) or 0)
        level = int(get("level", 1) or 1)
        if xp <= 0:
            xp = int(get("total_clicks", 0) or 0)
        p = progress_for_xp(xp)
        
        return {
            "click_coins": get("click_coins", 0),
            "stars": get("stars", 0),
            "crystals": get("crystals", 0),
            "total_clicks": get("total_clicks", 0),
            "click_power": get("click_power", 1),
            "auto_clicker": bool(get("auto_clicker")),
            "max_energy": 1000 * (get("energy_multiplier") or 1),
            "energy": 1000 * (get("energy_multiplier") or 1),
            "theme": get("theme", "default"),
            "xp": xp,
            "level": p["level"],
            "first_name": get("first_name", ""),
            "username": get("username", ""),
            "created_at": get("created_at", ""),
            "streak_days": get("streak_days", 0),
            "referrals_count": get("referrals_count", 0),
            "tasks_completed": get("tasks_completed", 0)
        }
    return {
        "click_coins": 0, "stars": 0, "crystals": 0, "total_clicks": 0,
        "click_power": 1, "auto_clicker": False, "max_energy": 1000,
        "energy": 1000, "theme": "default", "xp": 0, "level": 1,
        "first_name": "", "username": "", "created_at": "",
        "streak_days": 0, "referrals_count": 0, "tasks_completed": 0
    }

@router.post("/api/save-clicks")
async def save_clicks(request: Request):
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
    theme = data.get("theme") or ""
    if len(theme) > 32:
        theme = theme[:32]
    
    conn = get_db()
    cursor = conn.cursor()
    
    old_total_clicks = 0
    old_xp = 0
    try:
        cursor.execute("SELECT total_clicks, xp FROM users WHERE telegram_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            old_total_clicks = int(row["total_clicks"] or 0)
            old_xp = int(row["xp"] or 0)
    except Exception:
        pass
    
    total_clicks = max(old_total_clicks, total_clicks_in)
    delta_clicks = max(0, total_clicks - old_total_clicks)
    xp_gain = delta_clicks
    
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
                click_power = ?, auto_clicker = ?, energy_multiplier = ?, theme = ?,
                xp = ?, level = ?, last_activity = CURRENT_TIMESTAMP
            WHERE telegram_id = ?
        """, (click_coins, stars, crystals, total_clicks, click_power, auto_clicker, energy_multiplier, theme, xp, level, user_id))
    except Exception as e:
        print(f"Error updating user: {e}")
    
    conn.commit()
    conn.close()
    return {"status": "ok", "xp": xp, "level": level}

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
        cursor.execute("""
            SELECT first_name, username, level, total_clicks, tasks_completed,
                   streak_days, click_power, referrals_count, created_at
            FROM users WHERE telegram_id = ?
        """, (user_id,))
        user = cursor.fetchone()
    except Exception:
        user = None
    
    conn.close()
    
    if user:
        return {
            "first_name": user["first_name"] or "Игрок",
            "username": user["username"],
            "level": user["level"] or 1,
            "total_clicks": user["total_clicks"] or 0,
            "tasks_completed": user["tasks_completed"] or 0,
            "streak_days": user["streak_days"] or 0,
            "click_power": user["click_power"] or 1,
            "referrals_count": user["referrals_count"] or 0,
            "created_at": user["created_at"] or ""
        }
    return {}

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
