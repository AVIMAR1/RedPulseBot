# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timedelta

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import User

router = Router()

_state: dict[int, tuple[str, datetime]] = {}
_ttl = timedelta(minutes=5)


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(v)))


def _pet_keyboard():
    b = InlineKeyboardBuilder()
    b.button(text="🍖 Покормить", callback_data="pet_feed")
    b.button(text="🎮 Поиграть", callback_data="pet_play")
    b.button(text="✏️ Переименовать", callback_data="pet_rename")
    b.adjust(2, 1)
    return b.as_markup()


def _pet_text(user: User) -> str:
    pet_type = getattr(user, "pet_type", None) or "cat"
    pet_name = getattr(user, "pet_name", None) or "Пульсик"
    pet_level = int(getattr(user, "pet_level", 1) or 1)
    pet_xp = int(getattr(user, "pet_xp", 0) or 0)
    hunger = _clamp(int(getattr(user, "pet_hunger", 0) or 0), 0, 100)
    happy = _clamp(int(getattr(user, "pet_happiness", 50) or 50), 0, 100)

    mood = "😊" if happy >= 70 else "😐" if happy >= 40 else "😢"
    hungry = "🍽" if hunger <= 30 else "🥺" if hunger <= 70 else "😵"

    return (
        f"🐾 <b>Твой питомец</b>\n\n"
        f"🧬 Вид: <b>{pet_type}</b>\n"
        f"📛 Имя: <b>{pet_name}</b>\n"
        f"⭐ Уровень: <b>{pet_level}</b> (XP: {pet_xp})\n\n"
        f"{mood} Счастье: <b>{happy}/100</b>\n"
        f"{hungry} Сытость: <b>{100 - hunger}/100</b>\n"
    )


def _ensure_pet(user: User):
    if not getattr(user, "pet_type", None):
        user.pet_type = "cat"
    if not getattr(user, "pet_name", None):
        user.pet_name = "Пульсик"
    if not getattr(user, "pet_level", None):
        user.pet_level = 1
    if getattr(user, "pet_hunger", None) is None:
        user.pet_hunger = 20
    if getattr(user, "pet_happiness", None) is None:
        user.pet_happiness = 60


@router.message(Command("pet"))
@router.message(F.text and F.text.strip() == "🐾 Питомец")
async def cmd_pet(message: types.Message, session: AsyncSession):
    uid = message.from_user.id
    res = await session.execute(select(User).where(User.telegram_id == uid))
    user = res.scalar_one_or_none()
    if not user:
        await message.answer("❌ Сначала /start")
        return
    _ensure_pet(user)
    await session.commit()
    await message.answer(_pet_text(user), parse_mode="HTML", reply_markup=_pet_keyboard())


@router.callback_query(lambda c: c.data and c.data.startswith("pet_"))
async def cb_pet(callback: types.CallbackQuery, session: AsyncSession):
    uid = callback.from_user.id
    res = await session.execute(select(User).where(User.telegram_id == uid))
    user = res.scalar_one_or_none()
    if not user:
        await callback.answer("Сначала /start", show_alert=True)
        return
    _ensure_pet(user)

    now = datetime.now()
    last = getattr(user, "pet_last_interaction", None)
    cooldown = timedelta(minutes=10)
    if callback.data in ("pet_feed", "pet_play") and last and hasattr(last, "timestamp"):
        if now - last < cooldown:
            left = int((cooldown - (now - last)).total_seconds() // 60) + 1
            await callback.answer(f"Питомец устал. Попробуй через {left} мин.", show_alert=True)
            return

    if callback.data == "pet_feed":
        user.pet_hunger = _clamp(int(user.pet_hunger or 0) - 25, 0, 100)
        user.pet_happiness = _clamp(int(user.pet_happiness or 0) + 5, 0, 100)
        user.pet_xp = int(user.pet_xp or 0) + 5
        user.pet_last_interaction = now
        await session.commit()
        await callback.answer("🍖 Питомец поел!")
    elif callback.data == "pet_play":
        user.pet_happiness = _clamp(int(user.pet_happiness or 0) + 15, 0, 100)
        user.pet_hunger = _clamp(int(user.pet_hunger or 0) + 10, 0, 100)
        user.pet_xp = int(user.pet_xp or 0) + 8
        user.pet_last_interaction = now
        await session.commit()
        await callback.answer("🎮 Вы поиграли!")
    elif callback.data == "pet_rename":
        _state[uid] = ("rename", now)
        await callback.message.answer("✏️ Введи новое имя питомца (до 32 символов).")
        await callback.answer()
        return

    # Авто-уровень питомца: каждые 100 XP
    user.pet_level = max(1, int(user.pet_xp or 0) // 100 + 1)
    await session.commit()

    try:
        await callback.message.edit_text(_pet_text(user), parse_mode="HTML", reply_markup=_pet_keyboard())
    except Exception:
        await callback.message.answer(_pet_text(user), parse_mode="HTML", reply_markup=_pet_keyboard())


@router.message(lambda m: m.text and m.from_user and m.from_user.id in _state)
async def pet_rename_input(message: types.Message, session: AsyncSession):
    uid = message.from_user.id
    st = _state.get(uid)
    if not st:
        return
    mode, ts = st
    if mode != "rename":
        return
    if datetime.now() - ts > _ttl:
        _state.pop(uid, None)
        return
    _state.pop(uid, None)

    name = (message.text or "").strip()
    if not name or len(name) > 32:
        await message.answer("Имя должно быть 1-32 символа.")
        return

    res = await session.execute(select(User).where(User.telegram_id == uid))
    user = res.scalar_one_or_none()
    if not user:
        await message.answer("❌ Сначала /start")
        return
    _ensure_pet(user)
    user.pet_name = name
    await session.commit()
    await message.answer("✅ Имя обновлено!")
    await message.answer(_pet_text(user), parse_mode="HTML", reply_markup=_pet_keyboard())

