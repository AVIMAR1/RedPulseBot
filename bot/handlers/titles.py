# -*- coding: utf-8 -*-
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import User, Title, UserTitle

router = Router()


@router.message(Command("titles"))
@router.message(F.text and F.text.strip() == "🎖 Титулы")
async def cmd_titles(message: types.Message, session: AsyncSession):
    uid = message.from_user.id
    u_res = await session.execute(select(User).where(User.telegram_id == uid))
    user = u_res.scalar_one_or_none()
    if not user:
        await message.answer("❌ Сначала введи /start")
        return

    ut_res = await session.execute(
        select(UserTitle.title_id).where(UserTitle.user_id == uid)
    )
    title_ids = [r[0] for r in ut_res.all()]

    if not title_ids:
        await message.answer(
            "🎖 <b>Титулы</b>\n\nПока у тебя нет титулов. Они выдаются за ачивки или админом.",
            parse_mode="HTML",
        )
        return

    t_res = await session.execute(
        select(Title).where(Title.id.in_(title_ids), Title.is_active == True).order_by(Title.id.asc())
    )
    titles = t_res.scalars().all()

    builder = InlineKeyboardBuilder()
    lines = ["🎖 <b>Твои титулы</b>\n"]
    current_id = getattr(user, "current_title_id", None)
    for t in titles[:30]:
        is_cur = (current_id == t.id)
        mark = "✅" if is_cur else "▫️"
        lines.append(f"{mark} <b>{t.name}</b>" + (f"\n<i>{t.description}</i>" if t.description else ""))
        if not is_cur:
            builder.button(text=f"Выбрать: {t.name}", callback_data=f"title_set_{t.id}")
    if current_id:
        builder.button(text="Снять титул", callback_data="title_clear")
    builder.adjust(1)

    await message.answer("\n\n".join(lines), parse_mode="HTML", reply_markup=builder.as_markup())


@router.callback_query(lambda c: c.data and (c.data.startswith("title_set_") or c.data == "title_clear"))
async def cb_set_title(callback: types.CallbackQuery, session: AsyncSession):
    uid = callback.from_user.id
    u_res = await session.execute(select(User).where(User.telegram_id == uid))
    user = u_res.scalar_one_or_none()
    if not user:
        await callback.answer("Сначала /start", show_alert=True)
        return

    if callback.data == "title_clear":
        user.current_title_id = None
        await session.commit()
        await callback.answer("Титул снят")
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    try:
        title_id = int(callback.data.split("_")[-1])
    except Exception:
        await callback.answer("Ошибка", show_alert=True)
        return

    # проверяем, что титул принадлежит пользователю
    ut_exists = await session.execute(
        select(UserTitle.id).where(UserTitle.user_id == uid, UserTitle.title_id == title_id)
    )
    if not ut_exists.scalar_one_or_none():
        await callback.answer("У тебя нет этого титула", show_alert=True)
        return

    t_res = await session.execute(select(Title).where(Title.id == title_id, Title.is_active == True))
    t = t_res.scalar_one_or_none()
    if not t:
        await callback.answer("Титул недоступен", show_alert=True)
        return

    user.current_title_id = title_id
    await session.commit()
    await callback.answer("Титул выбран ✅")
    # Обновлять весь список не обязательно — профиль покажет выбранный титул.

