from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models import Event, User
from core.progression import progress_for_xp


def _loads_settings(s: str | None) -> dict:
    if not s:
        return {}
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


async def get_active_event_settings(session: AsyncSession) -> list[dict]:
    now = datetime.now()
    res = await session.execute(
        select(Event).where(
            and_(
                Event.is_active == True,
                (Event.start_at.is_(None) | (Event.start_at <= now)),
                (Event.end_at.is_(None) | (Event.end_at >= now)),
            )
        )
    )
    events = res.scalars().all()
    return [_loads_settings(e.settings_json) for e in events]


def _combine_settings(settings_list: list[dict]) -> dict:
    combined: dict = {}
    for s in settings_list:
        for k, v in (s or {}).items():
            # для чисел берём максимум (чтобы не "перемножать" случайно)
            if isinstance(v, (int, float)):
                prev = combined.get(k)
                if prev is None or (isinstance(prev, (int, float)) and v > prev):
                    combined[k] = v
            else:
                combined[k] = v
    return combined


async def apply_event_bonuses(
    session: AsyncSession,
    user: User,
    daily: dict | None = None,
    random_bonus: dict | None = None,
) -> dict:
    """
    Применяет активные ивенты к наградам.
    Возвращает словарь "extra" — что дополнительно начислено.
    """
    if not user:
        return {}

    settings = _combine_settings(await get_active_event_settings(session))
    if not settings:
        return {}

    extra = {"coins": 0, "xp": 0, "stars": 0, "crystals": 0}

    # Множители ежедневной награды
    if daily and daily.get("given"):
        m_coins = float(settings.get("daily_coins_mult", 1.0) or 1.0)
        m_xp = float(settings.get("daily_xp_mult", 1.0) or 1.0)
        if m_coins > 1.0:
            add = int((daily.get("coins", 0) or 0) * (m_coins - 1.0))
            if add > 0:
                user.click_coins = int(user.click_coins or 0) + add
                extra["coins"] += add
        if m_xp > 1.0:
            add = int((daily.get("xp", 0) or 0) * (m_xp - 1.0))
            if add > 0:
                user.xp = int(getattr(user, "xp", 0) or 0) + add
                extra["xp"] += add

    # 8 марта: если указан gender='female', можно удвоить XP
    if str(getattr(user, "gender", "") or "").lower() in ("female", "f", "woman", "girl"):
        m_fx = float(settings.get("female_xp_mult", 1.0) or 1.0)
        if m_fx > 1.0 and daily and daily.get("given"):
            add = int((daily.get("xp", 0) or 0) * (m_fx - 1.0))
            if add > 0:
                user.xp = int(getattr(user, "xp", 0) or 0) + add
                extra["xp"] += add

    # пересчёт уровня, если XP менялся
    if extra["xp"] > 0:
        user.level = progress_for_xp(int(getattr(user, "xp", 0) or 0))["level"]

    return extra

