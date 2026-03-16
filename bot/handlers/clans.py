# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timedelta

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import User, Clan, ClanMember

router = Router()

# Простые состояния ввода (локально; можно заменить на FSM позже)
_state: dict[int, tuple[str, datetime]] = {}  # user_id -> (mode, ts)
_ttl = timedelta(minutes=5)


async def _get_user_clan(session: AsyncSession, user_id: int) -> Clan | None:
    cm = await session.execute(select(ClanMember).where(ClanMember.user_id == user_id))
    member = cm.scalar_one_or_none()
    if not member:
        return None
    c = await session.execute(select(Clan).where(Clan.id == member.clan_id, Clan.is_active == True))
    return c.scalar_one_or_none()


def _clan_menu(has_clan: bool):
    b = InlineKeyboardBuilder()
    if has_clan:
        b.button(text="👥 Участники", callback_data="clan_members")
        b.button(text="🚪 Покинуть клан", callback_data="clan_leave")
    else:
        b.button(text="➕ Создать клан", callback_data="clan_create")
        b.button(text="🔎 Вступить по тегу", callback_data="clan_join")
        b.button(text="🎯 Рекомендации", callback_data="clan_recs")
    b.adjust(1)
    return b.as_markup()


@router.message(Command("clan"))
@router.message(F.text and F.text.strip() == "🏰 Клан")
async def cmd_clan(message: types.Message, session: AsyncSession):
    uid = message.from_user.id
    u_res = await session.execute(select(User).where(User.telegram_id == uid))
    user = u_res.scalar_one_or_none()
    if not user:
        await message.answer("❌ Сначала /start")
        return

    clan = await _get_user_clan(session, uid)
    if not clan:
        await message.answer(
            "🏰 <b>Кланы</b>\n\n"
            "Ты пока не состоишь в клане.\n"
            "Можешь создать свой или вступить по тегу.",
            parse_mode="HTML",
            reply_markup=_clan_menu(False),
        )
        return

    # количество участников
    members_res = await session.execute(select(ClanMember.id).where(ClanMember.clan_id == clan.id))
    members_count = len(members_res.all())
    await message.answer(
        "🏰 <b>Твой клан</b>\n\n"
        f"🏷 <b>{clan.name}</b>" + (f" <code>[{clan.tag}]</code>" if clan.tag else "") + "\n"
        f"👑 Глава: <code>{clan.owner_id}</code>\n"
        f"👥 Участников: <b>{members_count}</b>\n\n"
        f"🏦 Казна: {clan.treasury_coins} 🪙 | {clan.treasury_stars} ⭐ | {clan.treasury_crystals} 💎\n",
        parse_mode="HTML",
        reply_markup=_clan_menu(True),
    )


@router.callback_query(lambda c: c.data in ("clan_create", "clan_join", "clan_leave"))
async def clan_actions(callback: types.CallbackQuery, session: AsyncSession):
    uid = callback.from_user.id
    clan = await _get_user_clan(session, uid)

    if callback.data == "clan_leave":
        if not clan:
            await callback.answer("Ты не в клане", show_alert=True)
            return
        if int(clan.owner_id) == int(uid):
            await callback.answer("Глава не может покинуть клан. Передай лидерство или распусти клан через админку.", show_alert=True)
            return
        await session.execute(
            ClanMember.__table__.delete().where(ClanMember.user_id == uid)
        )
        await session.commit()
        await callback.answer("Ты покинул клан ✅")
        try:
            await callback.message.edit_text(
                "🏰 Ты покинул клан.", parse_mode="HTML", reply_markup=_clan_menu(False)
            )
        except Exception:
            pass
        return

    if clan:
        await callback.answer("Сначала покинь текущий клан", show_alert=True)
        return

    if callback.data == "clan_create":
        _state[uid] = ("create", datetime.now())
        await callback.message.edit_text(
            "➕ <b>Создание клана</b>\n\n"
            "Отправь одним сообщением:\n"
            "<code>Название | Тег</code>\n\n"
            "Пример: <code>Red Pulse Army | RPA</code>\n"
            "Тег — 2-6 символов (A-Z/0-9).",
            parse_mode="HTML",
        )
        await callback.answer()
        return

    if callback.data == "clan_join":
        _state[uid] = ("join", datetime.now())
        await callback.message.edit_text(
            "🔎 <b>Вступление в клан</b>\n\n"
            "Отправь тег клана (например <code>RPA</code>).",
            parse_mode="HTML",
        )
        await callback.answer()
        return


@router.callback_query(lambda c: c.data and (c.data == "clan_members" or c.data == "clan_recs" or c.data == "clan_recs_refresh" or c.data.startswith("clan_recs_join_")))
async def clan_extra(callback: types.CallbackQuery, session: AsyncSession):
    uid = callback.from_user.id
    clan = await _get_user_clan(session, uid)

    if callback.data == "clan_members":
        if not clan:
            await callback.answer("Ты не в клане", show_alert=True)
            return
        mem_res = await session.execute(
            select(User.telegram_id, User.first_name, User.username, ClanMember.role)
            .join(ClanMember, ClanMember.user_id == User.telegram_id)
            .where(ClanMember.clan_id == clan.id)
            .order_by(ClanMember.role.asc())
        )
        rows = mem_res.all()
        lines = [f"👥 <b>Участники клана</b> <b>{clan.name}</b>" + (f" <code>[{clan.tag}]</code>" if clan.tag else "") + "\n"]
        for tg_id, first_name, username, role in rows[:40]:
            name = first_name or f"User{tg_id}"
            at = f"@{username}" if username else ""
            r = "👑" if role == "leader" else "⭐" if role == "officer" else "•"
            lines.append(f"{r} <code>{tg_id}</code> {name} {at}")
        if len(rows) > 40:
            lines.append(f"\n…и ещё {len(rows) - 40} участников")
        await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=_clan_menu(True))
        await callback.answer()
        return

    # Рекомендации (10 случайных кланов)
    if callback.data in ("clan_recs", "clan_recs_refresh"):
        if clan:
            await callback.answer("Ты уже в клане", show_alert=True)
            return
        c_res = await session.execute(select(Clan).where(Clan.is_active == True))
        clans = c_res.scalars().all()
        import random
        random.shuffle(clans)
        pick = clans[:10]
        if not pick:
            await callback.message.edit_text("Пока нет активных кланов.", reply_markup=_clan_menu(False))
            await callback.answer()
            return
        b = InlineKeyboardBuilder()
        lines = ["🎯 <b>Рекомендованные кланы</b>\n"]
        for c in pick:
            lines.append(f"• <b>{c.name}</b> " + (f"<code>[{c.tag}]</code>" if c.tag else ""))
            if c.tag:
                b.button(text=f"Вступить [{c.tag}]", callback_data=f"clan_recs_join_{c.tag}")
        b.button(text="🔄 Обновить", callback_data="clan_recs_refresh")
        b.button(text="🔙 Назад", callback_data="clan_back_root")
        b.adjust(1)
        await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=b.as_markup())
        await callback.answer()
        return

    if callback.data.startswith("clan_recs_join_"):
        if clan:
            await callback.answer("Ты уже в клане", show_alert=True)
            return
        tag = callback.data.replace("clan_recs_join_", "").strip().upper()
        c_res = await session.execute(select(Clan).where(Clan.tag == tag, Clan.is_active == True))
        c = c_res.scalar_one_or_none()
        if not c:
            await callback.answer("Клан не найден", show_alert=True)
            return
        session.add(ClanMember(clan_id=c.id, user_id=uid, role="member"))
        try:
            await session.commit()
        except Exception:
            await session.rollback()
            await callback.answer("Не удалось вступить", show_alert=True)
            return
        await callback.answer("Вступил ✅")
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(f"✅ Ты вступил в клан <b>{c.name}</b> <code>[{c.tag}]</code>", parse_mode="HTML")
        return


@router.callback_query(lambda c: c.data == "clan_back_root")
async def clan_back_root(callback: types.CallbackQuery, session: AsyncSession):
    clan = await _get_user_clan(session, callback.from_user.id)
    await callback.message.edit_text(
        "🏰 <b>Кланы</b>\n\nВыбери действие:",
        parse_mode="HTML",
        reply_markup=_clan_menu(bool(clan)),
    )
    await callback.answer()


@router.message(lambda m: m.text and m.from_user and m.from_user.id in _state)
async def clan_text_input(message: types.Message, session: AsyncSession):
    uid = message.from_user.id
    st = _state.get(uid)
    if not st:
        return
    mode, ts = st
    if datetime.now() - ts > _ttl:
        _state.pop(uid, None)
        return
    _state.pop(uid, None)

    text = (message.text or "").strip()
    if mode == "create":
        if "|" not in text:
            await message.answer("Формат: <code>Название | Тег</code>", parse_mode="HTML")
            return
        name, tag = [p.strip() for p in text.split("|", 1)]
        if not name or len(name) > 64:
            await message.answer("Название слишком длинное/пустое.")
            return
        tag_norm = "".join(ch for ch in (tag or "").upper() if ch.isalnum())
        if len(tag_norm) < 2 or len(tag_norm) > 6:
            await message.answer("Тег должен быть 2-6 символов (A-Z/0-9).")
            return

        # проверим уникальность
        ex = await session.execute(select(Clan.id).where((Clan.name == name) | (Clan.tag == tag_norm)))
        if ex.scalar_one_or_none():
            await message.answer("Клан с таким именем/тегом уже существует.")
            return

        clan = Clan(name=name, tag=tag_norm, owner_id=uid, description=None)
        session.add(clan)
        await session.flush()
        session.add(ClanMember(clan_id=clan.id, user_id=uid, role="leader"))
        await session.commit()
        await message.answer(f"✅ Клан создан: <b>{name}</b> <code>[{tag_norm}]</code>", parse_mode="HTML")
        return

    if mode == "join":
        tag_norm = "".join(ch for ch in text.upper() if ch.isalnum())
        if len(tag_norm) < 2 or len(tag_norm) > 6:
            await message.answer("Неверный тег.")
            return
        c_res = await session.execute(select(Clan).where(Clan.tag == tag_norm, Clan.is_active == True))
        clan = c_res.scalar_one_or_none()
        if not clan:
            await message.answer("Клан не найден.")
            return
        # добавляем участника
        session.add(ClanMember(clan_id=clan.id, user_id=uid, role="member"))
        try:
            await session.commit()
        except Exception:
            await session.rollback()
            await message.answer("Не удалось вступить (возможно, уже в клане).")
            return
        await message.answer(f"✅ Ты вступил в клан <b>{clan.name}</b> <code>[{clan.tag}]</code>", parse_mode="HTML")
        return

