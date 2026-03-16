# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from aiogram import Router, types, F
from aiogram.filters import Command
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models import User, PromoCode, PromoRedemption

router = Router()

_awaiting_code: set[int] = set()


@router.message(Command("promo"))
async def cmd_promo(message: types.Message):
    _awaiting_code.add(message.from_user.id)
    await message.answer(
        "🎟 <b>Промокод</b>\n\n"
        "Отправь промокод одним сообщением.\n"
        "Пример: <code>REDPULSE2026</code>",
        parse_mode="HTML",
    )


@router.message(lambda m: m.text and not m.text.startswith("/") and m.from_user and m.from_user.id in _awaiting_code)
async def promo_message(message: types.Message, session: AsyncSession):
    uid = message.from_user.id
    if uid not in _awaiting_code:
        return
    _awaiting_code.discard(uid)

    code = (message.text or "").strip().upper()
    if not code or len(code) > 32:
        await message.answer("❌ Неверный промокод.")
        return

    user_result = await session.execute(select(User).where(User.telegram_id == uid))
    user = user_result.scalar_one_or_none()
    if not user:
        await message.answer("Сначала введи /start")
        return
    if user.is_banned:
        await message.answer("🚫 Доступ закрыт.")
        return

    promo_result = await session.execute(select(PromoCode).where(PromoCode.code == code))
    promo = promo_result.scalar_one_or_none()
    if not promo or not promo.is_active:
        await message.answer("❌ Промокод не найден или отключён.")
        return

    if promo.expires_at and promo.expires_at < datetime.now():
        await message.answer("⌛ Промокод истёк.")
        return

    if promo.max_uses and promo.used_count >= promo.max_uses:
        await message.answer("🚫 Лимит использований исчерпан.")
        return

    already = await session.execute(
        select(PromoRedemption).where(
            and_(PromoRedemption.promo_id == promo.id, PromoRedemption.user_id == uid)
        )
    )
    if already.scalar_one_or_none():
        await message.answer("❌ Ты уже использовал этот промокод.")
        return

    # Начисляем награды
    added = []
    if promo.reward_coins:
        user.click_coins += promo.reward_coins
        added.append(f"+{promo.reward_coins} 🪙")
    if promo.reward_stars:
        user.stars += promo.reward_stars
        added.append(f"+{promo.reward_stars} ⭐")
    if promo.reward_crystals:
        user.crystals += promo.reward_crystals
        added.append(f"+{promo.reward_crystals} 💎")

    promo.used_count += 1
    session.add(PromoRedemption(promo_id=promo.id, user_id=uid))
    await session.commit()

    if not added:
        await message.answer("✅ Промокод активирован (без награды).")
        return

    await message.answer(
        "✅ <b>Промокод активирован!</b>\n\n"
        f"Награда: {' '.join(added)}\n\n"
        "Проверить баланс: /profile",
        parse_mode="HTML",
    )

