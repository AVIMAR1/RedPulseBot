import random
import json
from aiogram import Router, types
from aiogram.filters import Command
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.utils.keyboard import InlineKeyboardBuilder

from models import User, Case, UserCase
from bot.keyboards import shop_menu

router = Router()

BOOSTS = {
    "energy": {"name": "🔋 Энергия +50%", "price": 500, "currency": "click_coins"},
    "power": {"name": "⚡ Сила x2", "price": 300, "currency": "click_coins"},
    "auto": {"name": "🤖 Автокликер", "price": 1000, "currency": "click_coins"},
    "crystal_boost": {"name": "💎 Кристальный буст", "price": 200, "currency": "crystals"}
}

SKINS = {
    "red_bg": {"name": "🔥 Красная тема", "price": 500, "currency": "crystals"},
    "gold_border": {"name": "👑 Золотая рамка", "price": 300, "currency": "crystals"},
    "click_effect": {"name": "✨ Эффект клика", "price": 200, "currency": "crystals"}
}

AVATARS = {
    "avatar1": {"name": "👨‍🚀 Космонавт", "price": 150, "currency": "crystals"},
    "avatar2": {"name": "🥷 Ниндзя", "price": 150, "currency": "crystals"},
    "avatar3": {"name": "👔 Бизнесмен", "price": 150, "currency": "crystals"}
}

@router.message(lambda message: message.text and message.text.strip() == "🛒 Магазин")
@router.message(Command("shop"))
async def cmd_shop(message: types.Message, session: AsyncSession):
    user_result = await session.execute(
        select(User).where(User.telegram_id == message.from_user.id)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        await message.answer("Сначала введи /start")
        return
    await message.answer(
        "🛒 <b>Магазин Red Pulse</b>\n\n"
        "🚀 <b>Бусты</b> — энергия, сила клика, автокликер (монеты и кристаллы)\n"
        "🎨 <b>Скины</b> — темы и рамки для кликера\n"
        "🖼️ <b>Аватарки</b> — уникальные иконки\n"
        "✨ <b>Эффекты</b> — визуальные плюшки\n\n"
        "📦 <b>Кейсы</b> — открой и получи случайную награду (звёзды, монеты, кристаллы).\n\n"
        "💎 Кристаллы: клики (1% шанс), обмен 100🪙=1💎, задания.\n"
        "🪙 Монеты: зарабатывай в кликере (/game).",
        parse_mode="HTML",
        reply_markup=shop_menu()
    )


@router.callback_query(lambda c: c.data == "shop_cases")
async def shop_cases(callback: types.CallbackQuery, session: AsyncSession):
    uid = callback.from_user.id
    cases_result = await session.execute(select(Case).where(Case.is_active == True))
    cases = cases_result.scalars().all()
    user_result = await session.execute(select(User).where(User.telegram_id == uid))
    user = user_result.scalar_one_or_none()
    if not user:
        await callback.answer("Ошибка")
        return
    # Количество кейсов у пользователя по case_id
    uc_result = await session.execute(
        select(UserCase.case_id, func.sum(UserCase.count).label("total"))
        .where(UserCase.user_id == uid)
        .group_by(UserCase.case_id)
    )
    counts = {row[0]: (row[1] or 0) for row in uc_result.all()}
    lines = ["📦 <b>Кейсы</b>\n\n"]
    builder = InlineKeyboardBuilder()
    for c in cases:
        n = counts.get(c.id, 0) or 0
        lines.append(f"• <b>{c.name}</b> — у тебя: {n} шт.")
        if c.price_coins:
            lines.append(f"  Купить: {c.price_coins} 🪙")
        if c.price_crystals:
            lines.append(f"  Купить: {c.price_crystals} 💎")
        if n > 0:
            builder.button(text=f"🎁 Открыть {c.name}", callback_data=f"open_case_{c.id}")
        # Покупка кейса (если цена указана)
        if (c.price_coins and (user.click_coins or 0) >= c.price_coins) or (c.price_crystals and (user.crystals or 0) >= c.price_crystals):
            builder.button(text=f"🛒 Купить {c.name}", callback_data=f"buy_case_{c.id}")
    builder.button(text="🔙 В меню магазина", callback_data="shop_back")
    builder.adjust(1)
    await callback.message.edit_text(
        "\n".join(lines) + "\n\nОткрой кейс — получи случайную награду!",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("buy_case_"))
async def buy_case(callback: types.CallbackQuery, session: AsyncSession):
    try:
        case_id = int(callback.data.split("_")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка", show_alert=True)
        return
    uid = callback.from_user.id
    case_result = await session.execute(select(Case).where(Case.id == case_id, Case.is_active == True))
    case = case_result.scalar_one_or_none()
    if not case:
        await callback.answer("Кейс не найден", show_alert=True)
        return
    user_result = await session.execute(select(User).where(User.telegram_id == uid))
    user = user_result.scalar_one_or_none()
    if not user:
        await callback.answer("Ошибка", show_alert=True)
        return
    # Оплата
    if case.price_coins and (user.click_coins or 0) >= case.price_coins:
        user.click_coins -= case.price_coins
    elif case.price_crystals and (user.crystals or 0) >= case.price_crystals:
        user.crystals -= case.price_crystals
    else:
        await callback.answer("❌ Недостаточно средств", show_alert=True)
        return
    session.add(UserCase(user_id=uid, case_id=case.id, count=1))
    await session.commit()
    await callback.answer("✅ Кейс куплен!", show_alert=True)
    # Обновим страницу кейсов
    await shop_cases(callback, session)


@router.callback_query(lambda c: c.data and c.data.startswith("open_case_"))
async def open_case(callback: types.CallbackQuery, session: AsyncSession):
    try:
        case_id = int(callback.data.split("_")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка")
        return
    uid = callback.from_user.id
    uc_result = await session.execute(
        select(UserCase).where(
            UserCase.user_id == uid,
            UserCase.case_id == case_id,
            UserCase.count > 0
        ).limit(1)
    )
    uc = uc_result.scalar_one_or_none()
    if not uc:
        await callback.answer("Нет такого кейса", show_alert=True)
        return
    case_result = await session.execute(select(Case).where(Case.id == case_id))
    case = case_result.scalar_one_or_none()
    if not case or not case.rewards_json:
        await callback.answer("Ошибка кейса")
        return
    try:
        rewards = json.loads(case.rewards_json)
    except (TypeError, json.JSONDecodeError):
        rewards = [{"type": "coins", "min": 50, "max": 150}]
    # Один случайный тип награды из списка
    r = random.choice(rewards)
    t = r.get("type", "coins")
    lo, hi = r.get("min", 0), r.get("max", 100)
    amount = random.randint(lo, hi) if hi >= lo else lo
    user_result = await session.execute(select(User).where(User.telegram_id == uid))
    user = user_result.scalar_one()
    if t == "coins":
        user.click_coins = (user.click_coins or 0) + amount
        msg = f"🪙 Монеты: +{amount}"
    elif t == "stars":
        user.stars = (user.stars or 0) + amount
        msg = f"⭐ Звёзды: +{amount}"
    elif t == "crystals":
        user.crystals = (user.crystals or 0) + amount
        msg = f"💎 Кристаллы: +{amount}"
    elif t == "theme":
        # theme reward: value in r["value"]
        theme = (r.get("value") or "default")[:32]
        user.theme = theme
        msg = f"🎨 Тема: {theme}"
    elif t == "boost_power":
        user.click_power = (user.click_power or 1) + max(1, amount)
        msg = f"⚡ Сила клика: +{max(1, amount)}"
    elif t == "boost_energy":
        user.energy_multiplier = (user.energy_multiplier or 1) + max(1, amount)
        msg = f"🔋 Энергия: +{max(1, amount)} уров."
    elif t == "boost_auto":
        user.auto_clicker = True
        msg = "🤖 Автокликер: активирован"
    else:
        user.click_coins = (user.click_coins or 0) + amount
        msg = f"🪙 Монеты: +{amount}"
    uc.count -= 1
    if uc.count <= 0:
        await session.delete(uc)
    await session.commit()
    await callback.answer()
    # Эффект: слот-машина в чат (анимация Telegram)
    try:
        await callback.message.answer_dice(emoji="🎰")
    except Exception:
        pass
    builder = InlineKeyboardBuilder()
    builder.button(text="📦 Кейсы", callback_data="shop_cases")
    builder.button(text="🔙 Магазин", callback_data="shop_back")
    await callback.message.edit_text(
        f"🎁 <b>{case.name}</b>\n\nТы получил: {msg}\n💰 Баланс обновлён.",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )

@router.callback_query(lambda c: c.data == "no_money")
async def shop_no_money(callback: types.CallbackQuery):
    await callback.answer("❌ Недостаточно средств", show_alert=True)


@router.callback_query(lambda c: c.data and c.data.startswith("buy_skin_"))
async def buy_skin(callback: types.CallbackQuery, session: AsyncSession):
    skin_id = callback.data.replace("buy_skin_", "")
    if skin_id not in SKINS:
        await callback.answer("Скин не найден", show_alert=True)
        return
    skin = SKINS[skin_id]
    user_result = await session.execute(
        select(User).where(User.telegram_id == callback.from_user.id)
    )
    user = user_result.scalar_one_or_none()
    if not user or user.crystals < skin["price"]:
        await callback.answer("❌ Недостаточно кристаллов", show_alert=True)
        return
    user.crystals -= skin["price"]
    await session.commit()
    await callback.message.edit_text(
        f"✅ Куплено: {skin['name']}\n\n"
        "Применяется в кликере (кнопка «Игра»).",
        parse_mode="HTML"
    )
    await callback.answer("🎉 Скин куплен!")


@router.callback_query(lambda c: c.data == "shop_boosts")
async def shop_boosts(callback: types.CallbackQuery, session: AsyncSession):
    user_result = await session.execute(
        select(User).where(User.telegram_id == callback.from_user.id)
    )
    user = user_result.scalar_one()
    
    builder = InlineKeyboardBuilder()
    for boost_id, boost in BOOSTS.items():
        price = boost["price"]
        currency = boost["currency"]
        currency_symbol = "🪙" if currency == "click_coins" else "💎"
        balance = user.click_coins if currency == "click_coins" else user.crystals
        
        button_text = f"{boost['name']} — {price}{currency_symbol}"
        if balance >= price:
            builder.button(text=button_text, callback_data=f"buy_boost_{boost_id}")
        else:
            builder.button(text=f"❌ {button_text}", callback_data="no_money")
    
    builder.adjust(1)
    
    await callback.message.edit_text(
        f"🚀 **Бусты для прокачки**\n\n"
        f"💰 Твой баланс:\n"
        f"🪙 Монеты: {user.click_coins}\n"
        f"💎 Кристаллы: {user.crystals}\n\n"
        f"Выбери буст:",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("buy_boost_"))
async def buy_boost(callback: types.CallbackQuery, session: AsyncSession):
    boost_id = callback.data.replace("buy_boost_", "")
    
    if boost_id not in BOOSTS:
        await callback.answer("❌ Буст не найден")
        return
    
    boost = BOOSTS[boost_id]
    telegram_id = callback.from_user.id
    
    user_result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = user_result.scalar_one()
    
    # Проверяем баланс
    balance = user.click_coins if boost["currency"] == "click_coins" else user.crystals
    if balance < boost["price"]:
        await callback.answer("❌ Недостаточно средств!")
        return
    
    # Списываем валюту
    if boost["currency"] == "click_coins":
        user.click_coins -= boost["price"]
    else:
        user.crystals -= boost["price"]
    
    # Применяем эффект буста
    if boost_id == "energy":
        user.energy_multiplier += 1
        effect_text = "🔋 Энергия увеличена на 50%!"
    elif boost_id == "power":
        user.click_power += 1
        effect_text = "⚡ Сила клика увеличена!"
    elif boost_id == "auto":
        user.auto_clicker = True
        effect_text = "🤖 Автокликер активирован!"
    elif boost_id == "crystal_boost":
        # Временный буст на кристаллы
        effect_text = "💎 Шанс кристаллов увеличен на 1% на 1 час!"
    
    await session.commit()
    
    await callback.message.edit_text(
        f"✅ **Покупка успешна!**\n\n"
        f"Ты приобрёл: {boost['name']}\n"
        f"{effect_text}\n\n"
        f"💰 Новый баланс:\n"
        f"🪙 Монеты: {user.click_coins}\n"
        f"💎 Кристаллы: {user.crystals}",
        parse_mode="Markdown"
    )
    await callback.answer("🎉 Поздравляем с покупкой!")

@router.callback_query(lambda c: c.data == "shop_skins")
async def shop_skins(callback: types.CallbackQuery, session: AsyncSession):
    user_result = await session.execute(
        select(User).where(User.telegram_id == callback.from_user.id)
    )
    user = user_result.scalar_one()
    
    builder = InlineKeyboardBuilder()
    for skin_id, skin in SKINS.items():
        price = skin["price"]
        balance = user.crystals
        button_text = f"{skin['name']} — {price}💎"
        
        if balance >= price:
            builder.button(text=button_text, callback_data=f"buy_skin_{skin_id}")
        else:
            builder.button(text=f"❌ {button_text}", callback_data="no_money")
    
    builder.adjust(1)
    
    builder.button(text="🔙 В меню магазина", callback_data="shop_back")
    builder.adjust(1)
    await callback.message.edit_text(
        f"🎨 <b>Скины для кликера</b>\n\n"
        f"💰 Баланс: {user.crystals} 💎\n\n"
        "Выбери скин:",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "shop_avatars")
async def shop_avatars(callback: types.CallbackQuery, session: AsyncSession):
    user_result = await session.execute(
        select(User).where(User.telegram_id == callback.from_user.id)
    )
    user = user_result.scalar_one_or_none()
    balance = user.crystals if user else 0
    lines = [f"💰 Баланс: {balance} 💎\n"]
    for aid, a in AVATARS.items():
        lines.append(f"• {a['name']} — {a['price']} 💎")
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 В меню магазина", callback_data="shop_back")
    await callback.message.edit_text(
        "🖼️ <b>Аватарки</b>\n\n" + "\n".join(lines) + "\n\n"
        "Покупай в кликере (кнопка «Игра»).",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "shop_effects")
async def shop_effects(callback: types.CallbackQuery, session: AsyncSession):
    user_result = await session.execute(
        select(User).where(User.telegram_id == callback.from_user.id)
    )
    user = user_result.scalar_one_or_none()
    balance = user.crystals if user else 0
    lines = [f"💰 Баланс: {balance} 💎\n"]
    for sid, s in SKINS.items():
        lines.append(f"• {s['name']} — {s['price']} 💎")
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 В меню магазина", callback_data="shop_back")
    await callback.message.edit_text(
        "✨ <b>Эффекты</b>\n\n" + "\n".join(lines) + "\n\n"
        "Покупай в кликере (кнопка «Игра»).",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "shop_back")
async def shop_back(callback: types.CallbackQuery, session: AsyncSession):
    user_result = await session.execute(
        select(User).where(User.telegram_id == callback.from_user.id)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        await callback.answer("Ошибка")
        return
    await callback.message.edit_text(
        "🛒 <b>Магазин Red Pulse</b>\n\n"
        "Выбери раздел:",
        parse_mode="HTML",
        reply_markup=shop_menu()
    )
    await callback.answer()