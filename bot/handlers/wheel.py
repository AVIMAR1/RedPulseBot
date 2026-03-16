# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta

from aiogram import Router, types, F
from aiogram.filters import Command
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import User, WheelConfig, UserWheel
from core.progression import progress_for_xp

router = Router()


def _default_segments():
    # weight: относительная вероятность
    return [
        {"code": "COINS_SMALL", "label": "🪙 +150", "weight": 40, "reward": {"coins": 150}},
        {"code": "COINS_MED", "label": "🪙 +400", "weight": 22, "reward": {"coins": 400}},
        {"code": "XP_SMALL", "label": "⭐ XP +60", "weight": 18, "reward": {"xp": 60}},
        {"code": "CRYSTAL", "label": "💎 +1", "weight": 8, "reward": {"crystals": 1}},
        {"code": "STARS", "label": "⭐ +2", "weight": 6, "reward": {"stars": 2}},
        {"code": "JACKPOT", "label": "💰 Джекпот (🪙 +2000)", "weight": 6, "reward": {"coins": 2000}},
    ]


def _pick_segment(segments: list[dict]) -> dict:
    weights = [max(0, int(s.get("weight", 1) or 1)) for s in segments]
    if not any(weights):
        return segments[0]
    return random.choices(segments, weights=weights, k=1)[0]


def _loads_json(s: str | None, default):
    if not s:
        return default
    try:
        return json.loads(s)
    except Exception:
        return default


@router.message(Command("wheel"))
@router.message(F.text and F.text.strip() == "🎡 Колесо")
async def cmd_wheel(message: types.Message, session: AsyncSession):
    uid = message.from_user.id
    u_res = await session.execute(select(User).where(User.telegram_id == uid))
    user = u_res.scalar_one_or_none()
    if not user:
        await message.answer("❌ Сначала /start")
        return

    cfg_res = await session.execute(select(WheelConfig).where(WheelConfig.is_active == True).order_by(WheelConfig.id.desc()))
    cfg = cfg_res.scalar_one_or_none()
    cooldown_hours = int(getattr(cfg, "cooldown_hours", 24) or 24) if cfg else 24
    segments = _loads_json(getattr(cfg, "segments_json", None) if cfg else None, _default_segments())
    if not isinstance(segments, list) or not segments:
        segments = _default_segments()

    uw_res = await session.execute(select(UserWheel).where(UserWheel.user_id == uid))
    uw = uw_res.scalar_one_or_none()
    if not uw:
        uw = UserWheel(user_id=uid)
        session.add(uw)
        await session.commit()

    now = datetime.now()
    if uw.last_spin_at and hasattr(uw.last_spin_at, "timestamp"):
        diff = now - uw.last_spin_at
        cd = timedelta(hours=cooldown_hours)
        if diff < cd:
            left = cd - diff
            h = int(left.total_seconds() // 3600)
            m = int((left.total_seconds() % 3600) // 60)
            await message.answer(f"⏳ Колесо можно крутить раз в {cooldown_hours}ч.\nОсталось: {h}ч {m}м.")
            return

    seg = _pick_segment(segments)
    reward = seg.get("reward") or {}
    coins = int(reward.get("coins", 0) or 0)
    xp = int(reward.get("xp", 0) or 0)
    stars = int(reward.get("stars", 0) or 0)
    crystals = int(reward.get("crystals", 0) or 0)

    # "Джекпот если 3 одинаковых подряд"
    history = _loads_json(getattr(uw, "last_results_json", None), [])
    if not isinstance(history, list):
        history = []
    history = (history + [seg.get("code")])[-3:]
    uw.last_results_json = json.dumps(history, ensure_ascii=False)

    triple = (len(history) == 3 and history[0] == history[1] == history[2])
    triple_bonus = 0
    if triple and seg.get("code") != "JACKPOT":
        triple_bonus = 1000
        coins += triple_bonus

    if coins:
        user.click_coins = int(user.click_coins or 0) + coins
    if stars:
        user.stars = int(user.stars or 0) + stars
    if crystals:
        user.crystals = int(user.crystals or 0) + crystals
    if xp:
        user.xp = int(getattr(user, "xp", 0) or 0) + xp
        user.level = progress_for_xp(int(user.xp or 0))["level"]

    uw.last_spin_at = now
    await session.commit()

    text = (
        "🎡 <b>Колесо фортуны</b>\n\n"
        f"Выпало: <b>{seg.get('label', 'Приз')}</b>\n\n"
        f"Награда: "
        + (f"🪙 +{coins} " if coins else "")
        + (f"⭐ +{stars} " if stars else "")
        + (f"💎 +{crystals} " if crystals else "")
        + (f"⭐ XP +{xp} " if xp else "")
    )
    if triple_bonus:
        text += f"\n\n🎉 <b>Три подряд!</b> Доп. бонус: 🪙 +{triple_bonus}"
    await message.answer(text, parse_mode="HTML")

