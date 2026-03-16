# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timedelta

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models import User, AuctionLot, AuctionBid

router = Router()


async def _get_active_lot(session: AsyncSession) -> AuctionLot | None:
    now = datetime.now()
    res = await session.execute(
        select(AuctionLot)
        .where(and_(AuctionLot.status == "active", AuctionLot.start_at <= now, AuctionLot.end_at >= now))
        .order_by(AuctionLot.end_at.asc())
    )
    return res.scalars().first()


def _bid_keyboard(lot: AuctionLot):
    b = InlineKeyboardBuilder()
    cur = int(lot.winner_bid or 0)
    base = max(int(lot.min_bid or 0), cur + 10)
    plus5 = int(base * 1.05)
    plus10 = int(base * 1.10)
    b.button(text=f"Ставка {base} 🪙", callback_data=f"auc_bid_{base}")
    b.button(text=f"+5% → {plus5} 🪙", callback_data=f"auc_bid_{plus5}")
    b.button(text=f"+10% → {plus10} 🪙", callback_data=f"auc_bid_{plus10}")
    b.button(text="🔄 Обновить", callback_data="auc_refresh")
    b.adjust(1)
    return b.as_markup()


@router.message(Command("auction"))
@router.message(F.text and F.text.strip() == "🧾 Аукцион")
async def cmd_auction(message: types.Message, session: AsyncSession):
    lot = await _get_active_lot(session)
    if not lot:
        await message.answer("🧾 <b>Аукцион</b>\n\nСейчас нет активных лотов.", parse_mode="HTML")
        return

    left = lot.end_at - datetime.now()
    mins = max(0, int(left.total_seconds() // 60))
    await message.answer(
        "🧾 <b>Аукцион</b>\n\n"
        f"🎁 Лот: <b>{lot.name}</b>\n"
        f"{lot.description or ''}\n\n"
        f"⏳ До конца: ~{mins} мин.\n"
        f"💸 Мин. ставка: {lot.min_bid} 🪙\n"
        f"🏷 Текущая ставка: {lot.winner_bid or 0} 🪙\n\n"
        "Сделай ставку кнопкой ниже:",
        parse_mode="HTML",
        reply_markup=_bid_keyboard(lot),
    )


@router.callback_query(lambda c: c.data in ("auc_refresh",) or (c.data and c.data.startswith("auc_bid_")))
async def auc_callbacks(callback: types.CallbackQuery, session: AsyncSession):
    uid = callback.from_user.id
    lot = await _get_active_lot(session)
    if not lot:
        await callback.answer("Нет активного лота", show_alert=True)
        return

    if callback.data == "auc_refresh":
        try:
            left = lot.end_at - datetime.now()
            mins = max(0, int(left.total_seconds() // 60))
            await callback.message.edit_text(
                "🧾 <b>Аукцион</b>\n\n"
                f"🎁 Лот: <b>{lot.name}</b>\n"
                f"{lot.description or ''}\n\n"
                f"⏳ До конца: ~{mins} мин.\n"
                f"💸 Мин. ставка: {lot.min_bid} 🪙\n"
                f"🏷 Текущая ставка: {lot.winner_bid or 0} 🪙\n\n"
                "Сделай ставку кнопкой ниже:",
                parse_mode="HTML",
                reply_markup=_bid_keyboard(lot),
            )
        except Exception:
            pass
        await callback.answer("Обновлено")
        return

    try:
        amount = int(callback.data.split("_")[-1])
    except Exception:
        await callback.answer("Ошибка ставки", show_alert=True)
        return

    u_res = await session.execute(select(User).where(User.telegram_id == uid))
    user = u_res.scalar_one_or_none()
    if not user:
        await callback.answer("Сначала /start", show_alert=True)
        return

    amount = max(0, amount)
    if amount < int(lot.min_bid or 0):
        await callback.answer(f"Минимум {lot.min_bid} 🪙", show_alert=True)
        return
    min_next = int(lot.winner_bid or 0) + 10
    if amount < min_next:
        await callback.answer(f"Нужно ≥ {min_next} 🪙", show_alert=True)
        return
    if int(user.click_coins or 0) < amount:
        await callback.answer("Недостаточно монет", show_alert=True)
        return

    prev_uid = lot.winner_user_id
    prev_bid = int(lot.winner_bid or 0)

    # списываем с нового лидера
    user.click_coins = int(user.click_coins or 0) - amount

    # возвращаем предыдущему лидеру
    if prev_uid and prev_bid > 0:
        if int(prev_uid) == int(uid):
            user.click_coins += prev_bid
        else:
            prev_res = await session.execute(select(User).where(User.telegram_id == prev_uid))
            prev_user = prev_res.scalar_one_or_none()
            if prev_user:
                prev_user.click_coins = int(prev_user.click_coins or 0) + prev_bid

    lot.winner_user_id = uid
    lot.winner_bid = amount
    session.add(AuctionBid(lot_id=lot.id, user_id=uid, amount=amount))
    await session.commit()

    # уведомим предыдущего лидера, что ставку перебили (+5% кнопка)
    if prev_uid and prev_bid > 0 and int(prev_uid) != int(uid):
        try:
            b = InlineKeyboardBuilder()
            up = int(amount * 1.05)
            b.button(text=f"Перебить +5% → {up} 🪙", callback_data=f"auc_bid_{up}")
            b.button(text="Открыть аукцион", callback_data="auc_refresh")
            b.adjust(1)
            await callback.bot.send_message(
                int(prev_uid),
                "⚠️ <b>Твою ставку перебили!</b>\n\n"
                f"🎁 Лот: <b>{lot.name}</b>\n"
                f"Новая ставка: <b>{amount}</b> 🪙\n",
                parse_mode="HTML",
                reply_markup=b.as_markup(),
            )
        except Exception:
            pass

    await callback.answer("Ставка принята ✅")
    # обновим карточку аукциона
    try:
        left = lot.end_at - datetime.now()
        mins = max(0, int(left.total_seconds() // 60))
        await callback.message.edit_text(
            "🧾 <b>Аукцион</b>\n\n"
            f"🎁 Лот: <b>{lot.name}</b>\n"
            f"{lot.description or ''}\n\n"
            f"⏳ До конца: ~{mins} мин.\n"
            f"💸 Мин. ставка: {lot.min_bid} 🪙\n"
            f"🏷 Текущая ставка: {lot.winner_bid or 0} 🪙\n\n"
            f"💰 Твой баланс: {user.click_coins} 🪙\n\n"
            "Сделай ставку кнопкой ниже:",
            parse_mode="HTML",
            reply_markup=_bid_keyboard(lot),
        )
    except Exception:
        pass

