# -*- coding: utf-8 -*-
"""
Казино: удвоение, кости (с эмодзи Telegram 🎲), ручная ставка с лимитами.
Лимиты ставки: мин 10, макс 5000 или 50% баланса (с учётом заработка в кликере).
"""
import random
import asyncio
from datetime import datetime, timedelta
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import User

router = Router()

# Лимиты ставок (монеты из кликера)
BET_MIN = 10
BET_MAX_ABS = 5000
BET_MAX_PCT = 0.5  # макс 50% баланса

DOUBLE_WIN_CHANCE = 0.48
DICE_WIN_THRESHOLD = 4  # 4, 5, 6 = выигрыш

# Ожидание своей ставки: user_id -> (game_type, timestamp)
_casino_bet_state: dict[int, tuple[str, datetime]] = {}
_STATE_TTL = timedelta(minutes=5)

# Блэкджек: user_id -> {deck, player_hand, dealer_hand, bet}
_bj_games: dict[int, dict] = {}
_BJ_TTL = timedelta(minutes=10)

# Колода: масть не важна для очков, значения 2-14 (11=J,12=Q,13=K,14=A)
def _make_deck():
    return [v for _ in range(4) for v in range(2, 15)]

def _card_str(v: int) -> str:
    if v == 14:
        return "A"
    if v == 13:
        return "K"
    if v == 12:
        return "Q"
    if v == 11:
        return "J"
    return str(v)

def _hand_value(hand: list[int]) -> int:
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


def _casino_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="🎯 Кости (кубик 4–6 = x2)", callback_data="casino_menu_dice")
    builder.button(text="🎰 Однорукий бандит", callback_data="casino_menu_slots")
    builder.button(text="🃏 21 очко (блэкджек)", callback_data="casino_menu_bj")
    builder.adjust(1)
    return builder.as_markup()


def _bet_buttons(prefix: str, balance: int):
    """Кнопки ставок + своя ставка. Лимит: min 10, max min(5000, 50% баланса)."""
    max_bet = min(BET_MAX_ABS, max(BET_MIN, int(balance * BET_MAX_PCT)))
    builder = InlineKeyboardBuilder()
    for amount in (10, 50, 100, 500, 1000):
        if amount <= balance and amount <= max_bet:
            builder.button(text=f"{amount} 🪙", callback_data=f"{prefix}_{amount}")
    if max_bet > 1000:
        builder.button(text=f"{max_bet} 🪙 (макс)", callback_data=f"{prefix}_{max_bet}")
    # prefix = "casino_slots"|"casino_dice"|"casino_bj" -> для своей ставки передаём short key
    if "slots" in prefix:
        short = "slots"
    elif "dice" in prefix:
        short = "dice"
    else:
        short = "bj"
    builder.button(text="✏️ Своя ставка", callback_data=f"casino_custom_{short}")
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def _validate_bet(amount: int, balance: int) -> tuple[bool, str]:
    if amount < BET_MIN:
        return False, f"Минимум {BET_MIN} 🪙"
    max_bet = min(BET_MAX_ABS, max(BET_MIN, int(balance * BET_MAX_PCT)))
    if amount > max_bet:
        return False, f"Максимум {max_bet} 🪙 (50% баланса или 5000)"
    if amount > balance:
        return False, f"Недостаточно монет. Баланс: {balance} 🪙"
    return True, ""


@router.message(Command("casino"))
@router.message(F.text and F.text.strip() == "🎰 Казино")
async def cmd_casino(message: types.Message, session: AsyncSession):
    telegram_id = message.from_user.id
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        await message.answer("Сначала введи /start")
        return
    if user.is_banned:
        await message.answer("🚫 Доступ закрыт.")
        return
    balance = user.click_coins or 0
    await message.answer(
        f"🎰 <b>Казино Red Pulse</b>\n\n"
        f"💰 Баланс: <b>{balance}</b> 🪙\n\n"
        f"Лимиты ставки: от {BET_MIN} до min(5000, 50% баланса).\n\n"
        "• <b>Кости</b> — бросок кубика 🎲: 4–6 = x2.\n"
        "• <b>Однорукий бандит</b> — крутим 🎰, выплаты по комбинациям.\n"
        "• <b>21 очко</b> — блэкджек против дилера.",
        parse_mode="HTML",
        reply_markup=_casino_menu()
    )

@router.callback_query(lambda c: c.data == "casino_menu_dice")
async def casino_dice_menu(callback: types.CallbackQuery, session: AsyncSession):
    result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
    user = result.scalar_one_or_none()
    balance = (user.click_coins or 0) if user else 0
    await callback.message.edit_text(
        "🎯 <b>Кости</b>\n\n"
        f"💰 Баланс: {balance} 🪙\n"
        "Бросок кубика 🎲 в чат — 4, 5 или 6 = выигрыш x2.",
        parse_mode="HTML",
        reply_markup=_bet_buttons("casino_dice", balance)
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "casino_menu_slots")
async def casino_slots_menu(callback: types.CallbackQuery, session: AsyncSession):
    result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
    user = result.scalar_one_or_none()
    balance = (user.click_coins or 0) if user else 0
    await callback.message.edit_text(
        "🎰 <b>Однорукий бандит</b>\n\n"
        f"💰 Баланс: {balance} 🪙\n"
        "Платёжки:\n"
        "• 💎💎💎 x10\n"
        "• ⭐⭐⭐ x5\n"
        "• 🍒🍒🍒 x3\n"
        "• 🍒🍒? x2\n",
        parse_mode="HTML",
        reply_markup=_bet_buttons("casino_slots", balance)
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("casino_custom_"))
async def casino_custom_bet(callback: types.CallbackQuery, session: AsyncSession):
    """Запрос своей ставки: следующее сообщение с числом — ставка."""
    part = callback.data.replace("casino_custom_", "")
    if part == "slots":
        game_type = "slots"
    elif part == "dice":
        game_type = "dice"
    elif part == "bj":
        game_type = "bj"
    else:
        await callback.answer("Ошибка")
        return
    result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
    user = result.scalar_one_or_none()
    balance = (user.click_coins or 0) if user else 0
    max_bet = min(BET_MAX_ABS, max(BET_MIN, int(balance * BET_MAX_PCT)))
    _casino_bet_state[callback.from_user.id] = (game_type, datetime.now())
    await callback.message.edit_text(
        f"✏️ <b>Своя ставка</b>\n\n"
        f"Введи число от {BET_MIN} до {max_bet} (или до 50% баланса).\n"
        f"💰 Твой баланс: {balance} 🪙",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(F.text.func(lambda t: t.strip().isdigit()))
async def casino_bet_message(message: types.Message, session: AsyncSession):
    """Обработка введённой ставки (число в чат)."""
    user_id = message.from_user.id
    state_entry = _casino_bet_state.get(user_id)
    if not state_entry:
        return
    game_type, created = state_entry
    if datetime.now() - created > _STATE_TTL:
        del _casino_bet_state[user_id]
        return
    del _casino_bet_state[user_id]
    try:
        amount = int(message.text.strip())
    except ValueError:
        await message.answer("Введи одно число, например 100.")
        return
    result = await session.execute(select(User).where(User.telegram_id == user_id))
    user = result.scalar_one_or_none()
    if not user or user.is_banned:
        await message.answer("Ошибка доступа.")
        return
    balance = user.click_coins or 0
    ok, err = _validate_bet(amount, balance)
    if not ok:
        await message.answer(err)
        return
    if game_type == "dice":
        await _play_dice_message(message, session, user, amount)
    elif game_type == "slots":
        await _play_slots_from_message(message, session, user, amount)
    else:
        await _start_bj_from_message(message, session, user, amount)

async def _play_slots_from_message(message: types.Message, session: AsyncSession, user: User, amount: int):
    balance = user.click_coins or 0
    user.click_coins = balance - amount
    await session.commit()
    try:
        await message.answer_dice(emoji="🎰")
    except Exception:
        pass
    await asyncio.sleep(3.5)
    reels = ["🍒", "🍋", "⭐", "💎"]
    weights = [55, 30, 12, 3]
    a, b, c = random.choices(reels, weights=weights, k=3)
    mult = 0
    if a == b == c == "💎":
        mult = 10
    elif a == b == c == "⭐":
        mult = 5
    elif a == b == c == "🍒":
        mult = 3
    elif (a == "🍒" and b == "🍒") or (b == "🍒" and c == "🍒") or (a == "🍒" and c == "🍒"):
        mult = 2
    if mult > 0:
        win_total = amount * mult
        user.click_coins = (user.click_coins or 0) + win_total
        res = f"✅ Комбинация: <b>{a} {b} {c}</b>\nВыигрыш: x{mult} (+{win_total - amount} 🪙)"
    else:
        res = f"❌ Комбинация: <b>{a} {b} {c}</b>\nПроигрыш: −{amount} 🪙"
    await session.commit()
    text = f"🎰 <b>Однорукий бандит</b>\n\n{res}\n💰 Баланс: {user.click_coins} 🪙"
    builder = InlineKeyboardBuilder()
    builder.button(text="🎰 Ещё раз", callback_data="casino_menu_slots")
    builder.button(text="🎰 В меню", callback_data="casino_back_menu")
    builder.adjust(1)
    await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())


async def _start_bj_from_message(message: types.Message, session: AsyncSession, user: User, amount: int):
    """Начать блэкджек после ввода своей ставки."""
    balance = user.click_coins or 0
    deck = _make_deck()
    random.shuffle(deck)
    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]
    user.click_coins = balance - amount
    await session.commit()
    uid = message.from_user.id
    _bj_games[uid] = {"deck": deck, "player": player, "dealer": dealer, "bet": amount, "ts": datetime.now()}
    text = (
        f"🃏 <b>21 очко</b>\n\n"
        f"Твоя рука: {' '.join(_card_str(c) for c in player)} = <b>{_hand_value(player)}</b>\n"
        f"Дилер: {_card_str(dealer[0])} ?\n\nСтавка: {amount} 🪙"
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Ещё", callback_data="casino_bj_hit")
    builder.button(text="✋ Хватит", callback_data="casino_bj_stand")
    builder.button(text="⏫ Удвоить", callback_data="casino_bj_double")
    builder.adjust(2, 1)
    await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())


async def _play_double(message: types.Message, session: AsyncSession, user: User, amount: int):
    balance = user.click_coins or 0
    won = random.random() < DOUBLE_WIN_CHANCE
    if won:
        user.click_coins = balance - amount + amount * 2
        text = f"🎲 <b>Удвоение</b>\n\n✅ Выигрыш! +{amount} 🪙\n💰 Баланс: {user.click_coins} 🪙"
    else:
        user.click_coins = balance - amount
        text = f"🎲 <b>Удвоение</b>\n\n❌ Не повезло. −{amount} 🪙\n💰 Баланс: {user.click_coins} 🪙"
    await session.commit()
    builder = InlineKeyboardBuilder()
    builder.button(text="🎲 Ещё раз", callback_data="casino_menu_double")
    builder.button(text="🎰 В меню", callback_data="casino_back_menu")
    builder.adjust(1)
    await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())


async def _play_dice_message(message: types.Message, session: AsyncSession, user: User, amount: int):
    """Кости: отправляем кубик в чат, результат берём из dice.value."""
    balance = user.click_coins or 0
    # Отправляем кубик — Telegram покажет анимацию, в ответе будет value 1–6
    dice_msg = await message.answer_dice(emoji="🎲")
    # Дождаться анимации
    await asyncio.sleep(3.5)
    roll = dice_msg.dice.value if dice_msg.dice else random.randint(1, 6)
    win = roll >= DICE_WIN_THRESHOLD
    if win:
        user.click_coins = balance - amount + amount * 2
        result_txt = f"Выпало <b>{roll}</b> — выигрыш! +{amount} 🪙"
    else:
        user.click_coins = balance - amount
        result_txt = f"Выпало <b>{roll}</b> — проигрыш. −{amount} 🪙"
    await session.commit()
    text = f"🎯 <b>Кости</b>\n\n{result_txt}\n💰 Баланс: {user.click_coins} 🪙"
    builder = InlineKeyboardBuilder()
    builder.button(text="🎯 Ещё раз", callback_data="casino_menu_dice")
    builder.button(text="🎰 В меню", callback_data="casino_back_menu")
    builder.adjust(1)
    await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())


@router.callback_query(lambda c: c.data and c.data.startswith("casino_dice_"))
async def casino_play_dice(callback: types.CallbackQuery, session: AsyncSession):
    """Кости по кнопке: отправляем кубик в чат, результат из dice.value."""
    try:
        amount = int(callback.data.split("_")[-1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка ставки", show_alert=True)
        return
    telegram_id = callback.from_user.id
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user or user.is_banned:
        await callback.answer("Ошибка", show_alert=True)
        return
    balance = user.click_coins or 0
    ok, err = _validate_bet(amount, balance)
    if not ok:
        await callback.answer(err, show_alert=True)
        return
    # Отправляем кубик в чат (анимация Telegram)
    dice_msg = await callback.message.answer_dice(emoji="🎲")
    await asyncio.sleep(3.5)
    roll = dice_msg.dice.value if dice_msg.dice else random.randint(1, 6)
    win = roll >= DICE_WIN_THRESHOLD
    if win:
        user.click_coins = balance - amount + amount * 2
        result_txt = f"Выпало <b>{roll}</b> — выигрыш! +{amount} 🪙"
    else:
        user.click_coins = balance - amount
        result_txt = f"Выпало <b>{roll}</b> — проигрыш. −{amount} 🪙"
    await session.commit()
    text = f"🎯 <b>Кости</b>\n\n{result_txt}\n💰 Баланс: {user.click_coins} 🪙"
    builder = InlineKeyboardBuilder()
    builder.button(text="🎯 Ещё раз", callback_data="casino_menu_dice")
    builder.button(text="🎰 В меню", callback_data="casino_back_menu")
    builder.adjust(1)
    await callback.message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("casino_slots_"))
async def casino_play_slots(callback: types.CallbackQuery, session: AsyncSession):
    """Слот-автомат: отправляем 🎰, ждём анимацию, затем считаем выигрыш по таблице."""
    try:
        amount = int(callback.data.split("_")[-1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка ставки", show_alert=True)
        return
    uid = callback.from_user.id
    result = await session.execute(select(User).where(User.telegram_id == uid))
    user = result.scalar_one_or_none()
    if not user or user.is_banned:
        await callback.answer("Ошибка", show_alert=True)
        return
    balance = user.click_coins or 0
    ok, err = _validate_bet(amount, balance)
    if not ok:
        await callback.answer(err, show_alert=True)
        return
    # Списываем ставку заранее
    user.click_coins = balance - amount
    await session.commit()

    await callback.answer()
    # Реальный Telegram-слот: берём dice.value (1..64) и детерминированно раскладываем в 3 барабана
    dice_msg = await callback.message.answer_dice(emoji="🎰")
    await asyncio.sleep(3.5)
    v = dice_msg.dice.value if dice_msg.dice else random.randint(1, 64)
    reels = ["🍒", "🍋", "⭐", "💎"]
    n = max(1, min(64, int(v))) - 1  # 0..63
    a = reels[n % 4]
    b = reels[(n // 4) % 4]
    c = reels[(n // 16) % 4]

    mult = 0
    if a == b == c == "💎":
        mult = 10
    elif a == b == c == "⭐":
        mult = 5
    elif a == b == c == "🍒":
        mult = 3
    elif (a == "🍒" and b == "🍒") or (b == "🍒" and c == "🍒") or (a == "🍒" and c == "🍒"):
        mult = 2

    if mult > 0:
        win_total = amount * mult
        user.click_coins = (user.click_coins or 0) + win_total
        res = f"✅ Комбинация: <b>{a} {b} {c}</b>\nВыигрыш: x{mult} (+{win_total - amount} 🪙)"
    else:
        res = f"❌ Комбинация: <b>{a} {b} {c}</b>\nПроигрыш: −{amount} 🪙"
    await session.commit()

    text = f"🎰 <b>Однорукий бандит</b>\n\n{res}\n💰 Баланс: {user.click_coins} 🪙"
    builder = InlineKeyboardBuilder()
    builder.button(text="🎰 Ещё раз", callback_data="casino_menu_slots")
    builder.button(text="🎰 В меню", callback_data="casino_back_menu")
    builder.adjust(1)
    await callback.message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())


@router.callback_query(lambda c: c.data == "casino_menu_bj")
async def casino_bj_menu(callback: types.CallbackQuery, session: AsyncSession):
    result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
    user = result.scalar_one_or_none()
    balance = (user.click_coins or 0) if user else 0
    await callback.message.edit_text(
        "🃏 <b>21 очко (блэкджек)</b>\n\n"
        f"💰 Баланс: {balance} 🪙\n"
        "Выбери ставку. Цель — набрать ближе к 21, чем дилер, не перебор.",
        parse_mode="HTML",
        reply_markup=_bet_buttons("casino_bj", balance)
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("casino_bj_"))
async def casino_bj_play(callback: types.CallbackQuery, session: AsyncSession):
    data = callback.data
    if data == "casino_bj_hit" or data == "casino_bj_stand" or data == "casino_bj_double":
        await _bj_act(callback, session, data.split("_")[-1])
        return
    try:
        amount = int(data.split("_")[-1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка", show_alert=True)
        return
    uid = callback.from_user.id
    result = await session.execute(select(User).where(User.telegram_id == uid))
    user = result.scalar_one_or_none()
    if not user or user.is_banned:
        await callback.answer("Ошибка", show_alert=True)
        return
    balance = user.click_coins or 0
    ok, err = _validate_bet(amount, balance)
    if not ok:
        await callback.answer(err, show_alert=True)
        return
    deck = _make_deck()
    random.shuffle(deck)
    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]
    user.click_coins = balance - amount
    await session.commit()
    _bj_games[uid] = {
        "deck": deck,
        "player": player,
        "dealer": dealer,
        "bet": amount,
        "ts": datetime.now(),
    }
    await _bj_render(callback.message, uid, user, show_dealer_one=True)
    await callback.answer()


async def _bj_render(msg, uid: int, user: User, show_dealer_one: bool = False):
    g = _bj_games.get(uid)
    if not g:
        return
    player_hand = g["player"]
    dealer_hand = g["dealer"]
    bet = g["bet"]
    pv = _hand_value(player_hand)
    if show_dealer_one:
        dealer_txt = f"{_card_str(dealer_hand[0])} ?"
        dv = _hand_value([dealer_hand[0]])
    else:
        dealer_txt = " ".join(_card_str(c) for c in dealer_hand)
        dv = _hand_value(dealer_hand)
    text = (
        f"🃏 <b>21 очко</b>\n\n"
        f"Твоя рука: {' '.join(_card_str(c) for c in player_hand)} = <b>{pv}</b>\n"
        f"Дилер: {dealer_txt}" + (f" = {dv}" if not show_dealer_one else "") + "\n\n"
        f"Ставка: {bet} 🪙"
    )
    builder = InlineKeyboardBuilder()
    if show_dealer_one and pv <= 21:
        builder.button(text="➕ Ещё", callback_data="casino_bj_hit")
        builder.button(text="✋ Хватит", callback_data="casino_bj_stand")
        if len(player_hand) == 2:
            builder.button(text="⏫ Удвоить", callback_data="casino_bj_double")
    builder.adjust(2, 1)
    try:
        await msg.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup() if builder.as_markup().inline_keyboard else None)
    except Exception:
        pass


async def _bj_act(callback: types.CallbackQuery, session: AsyncSession, act: str):
    uid = callback.from_user.id
    g = _bj_games.get(uid)
    if not g or datetime.now() - g.get("ts", datetime.now()) > _BJ_TTL:
        _bj_games.pop(uid, None)
        await callback.answer("Сессия истекла. Начни заново.", show_alert=True)
        return
    result = await session.execute(select(User).where(User.telegram_id == uid))
    user = result.scalar_one_or_none()
    if not user:
        await callback.answer("Ошибка")
        return
    deck = g["deck"]
    player = g["player"]
    dealer = g["dealer"]
    bet = g["bet"]
    if act == "hit":
        player.append(deck.pop())
        pv = _hand_value(player)
        if pv > 21:
            _bj_games.pop(uid, None)
            user.click_coins = (user.click_coins or 0)
            await session.commit()
            text = f"🃏 Перебор ({pv}). Ты проиграл {bet} 🪙\n💰 Баланс: {user.click_coins} 🪙"
            builder = InlineKeyboardBuilder()
            builder.button(text="🃏 Ещё партия", callback_data="casino_menu_bj")
            builder.button(text="🎰 В меню", callback_data="casino_back_menu")
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
            await callback.answer()
            return
        await _bj_render(callback.message, uid, user, show_dealer_one=True)
    elif act == "double":
        balance = user.click_coins or 0
        if balance < bet:
            await callback.answer("Недостаточно монет для удвоения", show_alert=True)
            return
        user.click_coins = balance - bet
        g["bet"] += bet
        g["ts"] = datetime.now()
        await session.commit()
        player.append(deck.pop())
        pv = _hand_value(player)
        if pv > 21:
            _bj_games.pop(uid, None)
            text = f"🃏 Удвоение, перебор ({pv}). Проигрыш {g['bet']} 🪙\n💰 Баланс: {user.click_coins} 🪙"
            builder = InlineKeyboardBuilder()
            builder.button(text="🃏 Ещё партия", callback_data="casino_menu_bj")
            builder.button(text="🎰 В меню", callback_data="casino_back_menu")
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
            await callback.answer()
            return
        act = "stand"
    if act == "stand":
        while _hand_value(dealer) < 17:
            dealer.append(deck.pop())
        pv = _hand_value(player)
        dv = _hand_value(dealer)
        _bj_games.pop(uid, None)
        total_bet = g["bet"]
        if dv > 21 or pv > dv:
            win = total_bet * 2
            user.click_coins = (user.click_coins or 0) + win
            result_txt = f"Победа! +{win - total_bet} 🪙"
        elif pv == dv:
            user.click_coins = (user.click_coins or 0) + total_bet
            result_txt = "Ничья, ставка возвращена."
        else:
            result_txt = f"Проигрыш. −{total_bet} 🪙"
        await session.commit()
        dealer_txt = " ".join(_card_str(c) for c in dealer)
        text = (
            f"🃏 <b>Итог</b>\n\n"
            f"Ты: {' '.join(_card_str(c) for c in player)} = {pv}\n"
            f"Дилер: {dealer_txt} = {dv}\n\n"
            f"{result_txt}\n💰 Баланс: {user.click_coins} 🪙"
        )
        builder = InlineKeyboardBuilder()
        builder.button(text="🃏 Ещё партия", callback_data="casino_menu_bj")
        builder.button(text="🎰 В меню", callback_data="casino_back_menu")
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(lambda c: c.data == "casino_back_menu")
async def casino_back(callback: types.CallbackQuery, session: AsyncSession):
    result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
    user = result.scalar_one_or_none()
    balance = (user.click_coins or 0) if user else 0
    await callback.message.edit_text(
        f"🎰 <b>Казино Red Pulse</b>\n\n💰 Баланс: <b>{balance}</b> 🪙\n\nВыбери игру:",
        parse_mode="HTML",
        reply_markup=_casino_menu()
    )
    await callback.answer()
