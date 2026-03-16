# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timedelta

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from models import User, UserNotice, UserNoticeMessage

router = Router()

_reply_state: dict[int, tuple[int, datetime]] = {}  # user_id -> (notice_id, ts)
_TTL = timedelta(minutes=10)


def _notice_kb(notice_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="✏️ Ответить", callback_data=f"notice_reply_{notice_id}")
    b.button(text="📋 История", callback_data=f"notice_view_{notice_id}")
    b.adjust(1)
    return b.as_markup()


@router.message(Command("notices"))
@router.message(F.text and F.text.strip() == "⚠️ Сообщения")
async def cmd_notices(message: types.Message, session: AsyncSession):
    uid = message.from_user.id
    u_res = await session.execute(select(User).where(User.telegram_id == uid))
    user = u_res.scalar_one_or_none()
    if not user:
        await message.answer("❌ Сначала /start")
        return

    res = await session.execute(
        select(UserNotice).where(UserNotice.user_id == uid).order_by(desc(UserNotice.last_activity)).limit(10)
    )
    notices = res.scalars().all()
    if not notices:
        await message.answer("⚠️ У тебя нет сообщений/предупреждений от администрации.")
        return

    lines = ["⚠️ <b>Сообщения от администрации</b>\n"]
    b = InlineKeyboardBuilder()
    for n in notices:
        t = "⚠️" if n.notice_type == "warning" else "📩"
        s = "✅" if n.status == "closed" else "🟢"
        subj = (n.subject or "Без темы")[:40]
        lines.append(f"{t} {s} <b>#{n.id}</b> — {subj}")
        b.button(text=f"Открыть #{n.id}", callback_data=f"notice_view_{n.id}")
    b.adjust(1)
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=b.as_markup())


@router.callback_query(lambda c: c.data and (c.data.startswith("notice_view_") or c.data.startswith("notice_reply_")))
async def notice_callbacks(callback: types.CallbackQuery, session: AsyncSession):
    uid = callback.from_user.id
    try:
        notice_id = int(callback.data.split("_")[-1])
    except Exception:
        await callback.answer("Ошибка", show_alert=True)
        return

    n_res = await session.execute(
        select(UserNotice).where(UserNotice.id == notice_id, UserNotice.user_id == uid)
    )
    notice = n_res.scalar_one_or_none()
    if not notice:
        await callback.answer("Не найдено", show_alert=True)
        return

    if callback.data.startswith("notice_reply_"):
        if notice.status == "closed":
            await callback.answer("Тикет закрыт админом", show_alert=True)
            return
        _reply_state[uid] = (notice_id, datetime.now())
        await callback.message.answer("✏️ Напиши ответ одним сообщением.")
        await callback.answer()
        return

    # view
    m_res = await session.execute(
        select(UserNoticeMessage)
        .where(UserNoticeMessage.notice_id == notice_id)
        .order_by(UserNoticeMessage.created_at.asc())
    )
    msgs = m_res.scalars().all()
    head = "⚠️ <b>Предупреждение</b>" if notice.notice_type == "warning" else "📩 <b>Сообщение</b>"
    text = f"{head} <b>#{notice.id}</b>\n"
    if notice.subject:
        text += f"<i>{notice.subject}</i>\n"
    text += "\n<b>Переписка:</b>\n"
    for m in msgs[-15:]:
        who = "🛠️ Админ" if m.sender_type == "admin" else "👤 Ты"
        t = m.created_at.strftime("%d.%m %H:%M") if hasattr(m.created_at, "strftime") else ""
        text += f"\n{who} ({t}):\n{m.message}\n"

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=_notice_kb(notice.id))
    await callback.answer()


@router.message(lambda m: m.text and m.from_user and m.from_user.id in _reply_state)
async def notice_reply_message(message: types.Message, session: AsyncSession):
    uid = message.from_user.id
    notice_id, ts = _reply_state.get(uid, (0, datetime.now()))
    if datetime.now() - ts > _TTL:
        _reply_state.pop(uid, None)
        return
    _reply_state.pop(uid, None)

    n_res = await session.execute(select(UserNotice).where(UserNotice.id == notice_id, UserNotice.user_id == uid))
    notice = n_res.scalar_one_or_none()
    if not notice or notice.status == "closed":
        await message.answer("Тикет закрыт.")
        return

    session.add(
        UserNoticeMessage(
            notice_id=notice_id,
            user_id=uid,
            sender_type="user",
            message=(message.text or "").strip(),
            is_read=False,
        )
    )
    notice.status = "waiting_admin"
    notice.last_activity = datetime.now()
    await session.commit()
    await message.answer("✅ Ответ отправлен администрации.")

