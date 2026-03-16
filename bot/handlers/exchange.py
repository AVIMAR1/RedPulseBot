# -*- coding: utf-8 -*-
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import User

router = Router()

STARS_RATE = 1000  # 1000 coins -> 1 star
CRYSTALS_RATE = 100  # 100 coins -> 1 crystal


def _menu():
    b = InlineKeyboardBuilder()
    b.button(text="⭐ Монеты → Звёзды", callback_data="ex_menu_stars")
    b.button(text="💎 Монеты → Кристаллы", callback_data="ex_menu_crystals")
    b.adjust(1)
    return b.as_markup()


def _amount_kb(prefix: str, max_amount: int):
    b = InlineKeyboardBuilder()
    for a in (100, 500, 1000, 5000, 10000):
        if a <= max_amount:
            b.button(text=f"{a} 🪙", callback_data=f"{prefix}_{a}")
    if max_amount > 0:
        b.button(text=f"{max_amount} 🪙 (макс)", callback_data=f"{prefix}_{max_amount}")
    b.button(text="🔙 Назад", callback_data="ex_back")
    b.adjust(2, 2, 1)
    return b.as_markup()


@router.message(Command("exchange"))
@router.message(F.text and F.text.strip() == "🔄 Обмен")
async def cmd_exchange(message: types.Message, session: AsyncSession):
    uid = message.from_user.id
    u_res = await session.execute(select(User).where(User.telegram_id == uid))
    user = u_res.scalar_one_or_none()
    if not user:
        await message.answer("❌ Сначала /start")
        return
    await message.answer(
        "🔄 <b>Обмен валют</b>\n\n"
        f"Твой баланс: <b>{user.click_coins or 0}</b> 🪙\n\n"
        f"Курс:\n"
        f"• {STARS_RATE} 🪙 → 1 ⭐\n"
        f"• {CRYSTALS_RATE} 🪙 → 1 💎\n\n"
        "Выбери направление обмена:",
        parse_mode="HTML",
        reply_markup=_menu(),
    )


@router.callback_query(lambda c: c.data in ("ex_menu_stars", "ex_menu_crystals", "ex_back"))
async def ex_menu(callback: types.CallbackQuery, session: AsyncSession):
    uid = callback.from_user.id
    u_res = await session.execute(select(User).where(User.telegram_id == uid))
    user = u_res.scalar_one_or_none()
    if not user:
        await callback.answer("Сначала /start", show_alert=True)
        return
    coins = int(user.click_coins or 0)
    if callback.data == "ex_back":
        await callback.message.edit_text(
            "🔄 <b>Обмен валют</b>\n\nВыбери направление обмена:",
            parse_mode="HTML",
            reply_markup=_menu(),
        )
        await callback.answer()
        return
    if callback.data == "ex_menu_stars":
        max_amount = (coins // STARS_RATE) * STARS_RATE
        await callback.message.edit_text(
            f"⭐ <b>Монеты → Звёзды</b>\n\n"
            f"Баланс: {coins} 🪙\n"
            f"Курс: {STARS_RATE} 🪙 → 1 ⭐\n\n"
            "Выбери сумму монет для обмена:",
            parse_mode="HTML",
            reply_markup=_amount_kb("ex_stars", max_amount),
        )
        await callback.answer()
        return
    if callback.data == "ex_menu_crystals":
        max_amount = (coins // CRYSTALS_RATE) * CRYSTALS_RATE
        await callback.message.edit_text(
            f"💎 <b>Монеты → Кристаллы</b>\n\n"
            f"Баланс: {coins} 🪙\n"
            f"Курс: {CRYSTALS_RATE} 🪙 → 1 💎\n\n"
            "Выбери сумму монет для обмена:",
            parse_mode="HTML",
            reply_markup=_amount_kb("ex_crystals", max_amount),
        )
        await callback.answer()
        return


@router.callback_query(lambda c: c.data and (c.data.startswith("ex_stars_") or c.data.startswith("ex_crystals_")))
async def ex_do(callback: types.CallbackQuery, session: AsyncSession):
    uid = callback.from_user.id
    u_res = await session.execute(select(User).where(User.telegram_id == uid))
    user = u_res.scalar_one_or_none()
    if not user:
        await callback.answer("Сначала /start", show_alert=True)
        return
    coins = int(user.click_coins or 0)
    data = callback.data
    try:
        amount = int(data.split("_")[-1])
    except Exception:
        await callback.answer("Ошибка суммы", show_alert=True)
        return
    amount = max(0, amount)
    if amount <= 0 or amount > coins:
        await callback.answer("Недостаточно монет", show_alert=True)
        return

    if data.startswith("ex_stars_"):
        add = amount // STARS_RATE
        if add <= 0:
            await callback.answer(f"Минимум {STARS_RATE} 🪙", show_alert=True)
            return
        user.click_coins = coins - (add * STARS_RATE)
        user.stars = int(user.stars or 0) + add
        await session.commit()
        await callback.message.edit_text(
            f"✅ Обмен выполнен!\n\n"
            f"⭐ +{add}\n"
            f"🪙 −{add * STARS_RATE}\n\n"
            f"Баланс: {user.click_coins} 🪙 | {user.stars} ⭐ | {user.crystals} 💎",
            parse_mode="HTML",
            reply_markup=_menu(),
        )
        await callback.answer()
        return

    if data.startswith("ex_crystals_"):
        add = amount // CRYSTALS_RATE
        if add <= 0:
            await callback.answer(f"Минимум {CRYSTALS_RATE} 🪙", show_alert=True)
            return
        user.click_coins = coins - (add * CRYSTALS_RATE)
        user.crystals = int(user.crystals or 0) + add
        await session.commit()
        await callback.message.edit_text(
            f"✅ Обмен выполнен!\n\n"
            f"💎 +{add}\n"
            f"🪙 −{add * CRYSTALS_RATE}\n\n"
            f"Баланс: {user.click_coins} 🪙 | {user.stars} ⭐ | {user.crystals} 💎",
            parse_mode="HTML",
            reply_markup=_menu(),
        )
        await callback.answer()
        return

