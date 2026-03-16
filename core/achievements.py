from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Achievement, UserAchievement, UserTitle, User, Title


def _get_metric_value(user: User, metric: str) -> int:
    metric = (metric or "").strip()
    if metric == "total_clicks":
        return int(user.total_clicks or 0)
    if metric == "streak_days":
        return int(getattr(user, "streak_days", 0) or 0)
    if metric == "stars":
        return int(user.stars or 0)
    if metric == "xp":
        return int(getattr(user, "xp", 0) or 0)
    if metric == "level":
        return int(getattr(user, "level", 1) or 1)
    return 0


async def check_and_grant_achievements(session: AsyncSession, user: User) -> list[str]:
    """
    Проверяет активные ачивки и выдаёт награды/титулы.
    Возвращает список строк-уведомлений (что выдано).
    """
    if not user:
        return []

    res = await session.execute(select(Achievement).where(Achievement.is_active == True))
    achs = res.scalars().all()
    if not achs:
        return []

    granted_messages: list[str] = []
    for ach in achs:
        value = _get_metric_value(user, ach.metric)
        if value < int(ach.threshold or 0):
            continue

        exists = await session.execute(
            select(UserAchievement.id).where(
                UserAchievement.user_id == user.telegram_id,
                UserAchievement.achievement_id == ach.id,
            )
        )
        if exists.scalar_one_or_none():
            continue

        session.add(UserAchievement(user_id=user.telegram_id, achievement_id=ach.id))

        # Награды валютами
        if int(ach.reward_coins or 0) > 0:
            user.click_coins = int(user.click_coins or 0) + int(ach.reward_coins or 0)
        if int(ach.reward_stars or 0) > 0:
            user.stars = int(user.stars or 0) + int(ach.reward_stars or 0)
        if int(ach.reward_crystals or 0) > 0:
            user.crystals = int(user.crystals or 0) + int(ach.reward_crystals or 0)

        # Титул
        if ach.reward_title_id:
            # Проверим, что титул существует и активен
            t_res = await session.execute(select(Title).where(Title.id == ach.reward_title_id))
            t = t_res.scalar_one_or_none()
            if t and t.is_active:
                # добавим владение
                ut_exists = await session.execute(
                    select(UserTitle.id).where(
                        UserTitle.user_id == user.telegram_id,
                        UserTitle.title_id == t.id,
                    )
                )
                if not ut_exists.scalar_one_or_none():
                    session.add(UserTitle(user_id=user.telegram_id, title_id=t.id, source="achievement"))
                # если у пользователя ещё нет выбранного титула — установим
                if not getattr(user, "current_title_id", None):
                    user.current_title_id = t.id

        granted_messages.append(f"🏆 Ачивка: {ach.name}")

    if granted_messages:
        await session.commit()
    return granted_messages

