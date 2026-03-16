# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import User, GlobalBank

router = Router()


def _kb(can_add: bool):
    b = InlineKeyboardBuilder()
    if can_add:
        for a in (100, 500, 1000, 5000):
            b.button(text=f"➕ {a} 🪙", callback_data=f"bank_add_{a}")
        b.button(text="➕ Макс", callback_data="bank_add_max")
    b.button(text="🔄 Обновить", callback_data="bank_refresh")
    b.adjust(2, 2, 1)
    return b.as_markup()


@router.message(Command("bank"))
@router.message(F.text and F.text.strip() == "🏦 Общая казна")
async def cmd_bank(message: types.Message, session: AsyncSession):
    uid = message.from_user.id
    u_res = await session.execute(select(User).where(User.telegram_id == uid))
    user = u_res.scalar_one_or_none()
    if not user:
        await message.answer("❌ Сначала /start")
        return
    b_res = await session.execute(select(GlobalBank).where(GlobalBank.id == 1))
    bank = b_res.scalar_one_or_none()
    if not bank:
        bank = GlobalBank(id=1, coins=0, xp=0, level=1, target=100_000)
        session.add(bank)
        await session.commit()

    bonus = ""
    if bank.bonus_active_until and bank.bonus_active_until > datetime.now():
        bonus = f"\n🔥 Бонус XP x2 активен до: {bank.bonus_active_until.strftime('%d.%m %H:%M')}"

    await message.answer(
        "🏦 <b>Общая казна</b>\n\n"
        f"🪙 В банке: <b>{bank.coins}</b>\n"
        f"🏆 Уровень банка: <b>{bank.level}</b>\n"
        f"🎯 Цель: <b>{bank.target}</b>\n"
        f"{bonus}\n\n"
        f"Твой баланс: <b>{user.click_coins or 0}</b> 🪙\n\n"
        "Ты можешь пополнить казну монетами. Когда цель заполняется — всем включается бонус.",
        parse_mode="HTML",
        reply_markup=_kb((user.click_coins or 0) >= 100),
    )


@router.callback_query(lambda c: c.data in ("bank_refresh", "bank_add_max") or (c.data and c.data.startswith("bank_add_")))
async def bank_cb(callback: types.CallbackQuery, session: AsyncSession):
    uid = callback.from_user.id
    u_res = await session.execute(select(User).where(User.telegram_id == uid))
    user = u_res.scalar_one_or_none()
    if not user:
        await callback.answer("Сначала /start", show_alert=True)
        return
    b_res = await session.execute(select(GlobalBank).where(GlobalBank.id == 1))
    bank = b_res.scalar_one_or_none()
    if not bank:
        bank = GlobalBank(id=1, coins=0, xp=0, level=1, target=100_000)
        session.add(bank)
        await session.commit()

    if callback.data.startswith("bank_add_") or callback.data == "bank_add_max":
        coins = int(user.click_coins or 0)
        if coins < 100:
            await callback.answer("Минимум 100 🪙", show_alert=True)
            return
        if callback.data == "bank_add_max":
            amount = min(coins, 50_000)
        else:
            try:
                amount = int(callback.data.split("_")[-1])
            except Exception:
                amount = 0
        amount = max(0, min(amount, coins))
        if amount < 100:
            await callback.answer("Минимум 100 🪙", show_alert=True)
            return
        user.click_coins = coins - amount
        bank.coins = int(bank.coins or 0) + amount

        # если цель достигнута — активируем бонус на 48 часов
        if int(bank.coins or 0) >= int(bank.target or 0):
            bank.coins = int(bank.coins or 0) - int(bank.target or 0)
            bank.level = int(bank.level or 1) + 1
            bank.target = int(int(bank.target or 100000) * 1.5) + 50_000
            bank.bonus_active_until = datetime.now() + timedelta(days=2)

        await session.commit()
        await callback.answer(f"Пополнено: +{amount} 🪙")

    bonus = ""
    if bank.bonus_active_until and bank.bonus_active_until > datetime.now():
        bonus = f"\n🔥 Бонус XP x2 активен до: {bank.bonus_active_until.strftime('%d.%m %H:%M')}"

    try:
        await callback.message.edit_text(
            "🏦 <b>Общая казна</b>\n\n"
            f"🪙 В банке: <b>{bank.coins}</b>\n"
            f"🏆 Уровень банка: <b>{bank.level}</b>\n"
            f"🎯 Цель: <b>{bank.target}</b>\n"
            f"{bonus}\n\n"
            f"Твой баланс: <b>{user.click_coins or 0}</b> 🪙",
            parse_mode="HTML",
            reply_markup=_kb((user.click_coins or 0) >= 100),
        )
    except Exception:
        pass
