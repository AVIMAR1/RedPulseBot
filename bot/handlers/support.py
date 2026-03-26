from aiogram import Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta

from models import User, SupportTicket, SupportMessage

router = Router()

# Состояние: выбор типа нового тикета
_new_ticket_type: dict[int, str] = {}

# Команда и кнопка меню для обращения в поддержку
@router.message(Command("support"))
@router.message(lambda m: m.text and m.text.strip() == "🆘 Поддержка")
async def cmd_support(message: types.Message, session: AsyncSession):
    telegram_id = message.from_user.id
    
    # Проверяем, не забанен ли пользователь
    user_result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = user_result.scalar_one_or_none()
    
    if not user:
        await message.answer("❌ Сначала введите /start")
        return
    
    if user.is_banned:
        await message.answer("🚫 Вы забанены и не можете обращаться в поддержку.")
        return
    
    # Получаем открытые тикеты пользователя
    tickets_result = await session.execute(
        select(SupportTicket)
        .where(
            and_(
                SupportTicket.user_id == telegram_id,
                SupportTicket.status.in_(['open', 'in_progress', 'waiting_user', 'waiting_admin'])
            )
        )
        .order_by(desc(SupportTicket.created_at))
    )
    open_tickets = tickets_result.scalars().all()
    
    # Получаем закрытые тикеты (последние 3 для истории)
    closed_tickets_result = await session.execute(
        select(SupportTicket)
        .where(
            and_(
                SupportTicket.user_id == telegram_id,
                SupportTicket.status == 'closed'
            )
        )
        .order_by(desc(SupportTicket.closed_at))
        .limit(3)
    )
    closed_tickets = closed_tickets_result.scalars().all()
    
    # Формируем клавиатуру
    builder = InlineKeyboardBuilder()
    
    if open_tickets:
        builder.button(text="📝 Новое обращение", callback_data="support_new")
        
        for ticket in open_tickets[:3]:
            status_emoji = {
                'open': '🟢',
                'in_progress': '🟡',
                'waiting_user': '🔴',
                'waiting_admin': '🟠'
            }.get(ticket.status, '⚪')
            
            subject = ticket.subject or "Без темы"
            if len(subject) > 20:
                subject = subject[:20] + "..."
            
            builder.button(
                text=f"{status_emoji} #{ticket.id} {subject}",
                callback_data=f"support_view_{ticket.id}"
            )
        
        builder.button(text="📋 Все мои обращения", callback_data="support_my_tickets")
    else:
        builder.button(text="📝 Связаться с поддержкой", callback_data="support_new")
    
    if closed_tickets:
        builder.button(text="📜 История тикетов", callback_data="support_history")
    
    builder.adjust(1)
    
    await message.answer(
        "🆘 **Поддержка Red Pulse**\n\n"
        "Здесь ты можешь задать вопрос, сообщить о проблеме или получить помощь.\n\n"
        "📌 **Как это работает:**\n"
        "• Создай обращение — мы ответим как можно скорее\n"
        "• Ты получишь уведомление, когда придёт ответ\n"
        "• После ответа ты можешь продолжить диалог\n"
        "• Если вопрос решён — закрой тикет\n\n"
        "⏳ Среднее время ответа: до 24 часов",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )

# Создание нового обращения
@router.callback_query(lambda c: c.data == "support_new")
async def support_new(callback: types.CallbackQuery, session: AsyncSession):
    builder = InlineKeyboardBuilder()
    builder.button(text="🚨 Жалоба", callback_data="support_type_complaint")
    builder.button(text="🐞 Баг/ошибка", callback_data="support_type_bug")
    builder.button(text="❓ Вопрос", callback_data="support_type_question")
    builder.button(text="🔙 Назад", callback_data="support_back")
    builder.adjust(1)
    await callback.message.edit_text(
        "📝 **Новое обращение в поддержку**\n\n"
        "Выбери тип обращения:",
        parse_mode="Markdown",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("support_type_"))
async def support_choose_type(callback: types.CallbackQuery, session: AsyncSession):
    uid = callback.from_user.id
    t = callback.data.replace("support_type_", "")
    if t not in ("complaint", "bug", "question"):
        t = "question"
    _new_ticket_type[uid] = t
    await callback.message.edit_text(
        "✏️ **Опиши проблему одним сообщением**\n\n"
        "Мы учтём выбранный тип тикета.",
        parse_mode="Markdown",
    )
    await callback.answer()

# Тексты кнопок меню — не создаём по ним тикет
MENU_BUTTON_TEXTS = {
    "🎮 Игра (Кликер)", "👤 Профиль", "📋 Задания", "🏆 Рейтинг",
    "🛒 Магазин", "🎰 Казино", "👥 Рефералы", "🆘 Поддержка",
    "🎖 Титулы", "🏰 Клан", "🐾 Питомец", "🎡 Колесо", "🧾 Аукцион",
    "🎮 Игры", "💰 Экономика", "👥 Соц", "🛠 Сервисы", "🏠 Меню",
    "🔄 Обмен", "🏦 Общая казна", "⚠️ Сообщения",
}

# Обработка текстовых сообщений для создания обращения (игнорируем нажатия кнопок меню)
@router.message(
    lambda m: m.text
    and not m.text.startswith("/")
    and m.text.strip() not in MENU_BUTTON_TEXTS
)
async def handle_support_message(message: types.Message, session: AsyncSession):
    telegram_id = message.from_user.id

    # Проверяем, есть ли у пользователя открытый тикет
    open_ticket = await session.execute(
        select(SupportTicket)
        .where(
            and_(
                SupportTicket.user_id == telegram_id,
                SupportTicket.status.in_(['open', 'waiting_admin', 'in_progress', 'waiting_user'])
            )
        )
        .order_by(desc(SupportTicket.created_at))
        .limit(1)
    )
    ticket = open_ticket.scalar_one_or_none()

    if ticket and ticket.status in ['waiting_user', 'waiting_admin', 'open', 'in_progress']:
        # Это ответ на сообщение поддержки — добавляем сообщение в тикет
        new_message = SupportMessage(
            ticket_id=ticket.id,
            user_id=telegram_id,
            sender_type='user',
            message=message.text
        )
        session.add(new_message)

        ticket.status = 'waiting_admin'
        ticket.last_activity = datetime.now()
        ticket.reminder_count = 0

        await session.commit()

        builder = InlineKeyboardBuilder()
        builder.button(text="📋 К моим обращениям", callback_data="support_my_tickets")

        await message.answer(
            "✅ **Сообщение отправлено!**\n\n"
            "Мы получили твой ответ и скоро свяжемся с тобой.\n"
            "Ты получишь уведомление, когда поддержка ответит.",
            parse_mode="Markdown",
            reply_markup=builder.as_markup()
        )

    elif telegram_id in _new_ticket_type:
        # Пользователь выбрал тип тикета — создаём новый тикет
        user_result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = user_result.scalar_one_or_none()

        if not user:
            await message.answer("❌ Сначала введите /start")
            return

        if user.is_banned:
            await message.answer("🚫 Вы забанены и не можете обращаться в поддержку.")
            return

        subject = message.text[:100] + ("..." if len(message.text) > 100 else "")
        ticket_type = _new_ticket_type.pop(telegram_id, "question")
        new_ticket = SupportTicket(
            user_id=telegram_id,
            subject=subject,
            status='open',
            reminder_count=0,
            ticket_type=ticket_type,
        )
        session.add(new_ticket)
        await session.flush()

        new_message = SupportMessage(
            ticket_id=new_ticket.id,
            user_id=telegram_id,
            sender_type='user',
            message=message.text
        )
        session.add(new_message)

        await session.commit()

        builder = InlineKeyboardBuilder()
        builder.button(text="📋 Мои обращения", callback_data="support_my_tickets")

        await message.answer(
            "✅ **Обращение создано!**\n\n"
            f"Номер тикета: #{new_ticket.id}\n\n"
            "Мы уже получили твой вопрос и ответим в ближайшее время.\n"
            "Ты получишь уведомление, когда поддержка ответит.\n\n"
            "📌 Ты всегда можешь посмотреть свои обращения по кнопке ниже.",
            parse_mode="Markdown",
            reply_markup=builder.as_markup()
        )

    else:
        # У пользователя нет открытого тикета и он не выбирал тип — игнорируем сообщение
        # Или предлагаем создать тикет через /support
        pass

# Просмотр всех обращений пользователя
@router.callback_query(lambda c: c.data == "support_my_tickets")
async def support_my_tickets(callback: types.CallbackQuery, session: AsyncSession):
    telegram_id = callback.from_user.id
    
    tickets_result = await session.execute(
        select(SupportTicket)
        .where(SupportTicket.user_id == telegram_id)
        .order_by(desc(SupportTicket.created_at))
    )
    tickets = tickets_result.scalars().all()
    
    if not tickets:
        await callback.message.edit_text(
            "📭 У тебя пока нет обращений в поддержку.\n\n"
            "Создай новое обращение, если нужна помощь!",
            parse_mode="Markdown"
        )
        await callback.answer()
        return
    
    builder = InlineKeyboardBuilder()
    
    for ticket in tickets[:10]:
        status_emoji = {
            'open': '🟢',
            'in_progress': '🟡',
            'waiting_user': '🔴',
            'waiting_admin': '🟠',
            'closed': '⚫'
        }.get(ticket.status, '⚪')
        
        status_text = {
            'open': 'Открыт',
            'in_progress': 'В работе',
            'waiting_user': 'Ожидает вас',
            'waiting_admin': 'Ожидает поддержку',
            'closed': 'Закрыт'
        }.get(ticket.status, ticket.status)
        
        created = ticket.created_at.strftime('%d.%m.%Y')
        subject = ticket.subject or "Без темы"
        if len(subject) > 30:
            subject = subject[:30] + "..."
        
        builder.button(
            text=f"{status_emoji} #{ticket.id} ({created}) - {status_text}\n{subject}",
            callback_data=f"support_view_{ticket.id}"
        )
    
    builder.button(text="🔙 Назад", callback_data="support_back")
    builder.adjust(1)
    
    await callback.message.edit_text(
        "📋 **Мои обращения в поддержку**\n\n"
        "Выбери тикет для просмотра:",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# История тикетов (закрытые)
@router.callback_query(lambda c: c.data == "support_history")
async def support_history(callback: types.CallbackQuery, session: AsyncSession):
    telegram_id = callback.from_user.id
    
    tickets_result = await session.execute(
        select(SupportTicket)
        .where(
            and_(
                SupportTicket.user_id == telegram_id,
                SupportTicket.status == 'closed'
            )
        )
        .order_by(desc(SupportTicket.closed_at))
        .limit(20)
    )
    tickets = tickets_result.scalars().all()
    
    if not tickets:
        await callback.message.edit_text(
            "📭 У тебя пока нет закрытых обращений.",
            parse_mode="Markdown"
        )
        await callback.answer()
        return
    
    builder = InlineKeyboardBuilder()
    
    for ticket in tickets:
        closed = ticket.closed_at.strftime('%d.%m.%Y') if ticket.closed_at else '?'
        subject = ticket.subject or "Без темы"
        if len(subject) > 30:
            subject = subject[:30] + "..."
        
        builder.button(
            text=f"📋 #{ticket.id} ({closed}) - {subject}",
            callback_data=f"support_view_{ticket.id}"
        )
    
    builder.button(text="🔙 Назад", callback_data="support_my_tickets")
    builder.adjust(1)
    
    await callback.message.edit_text(
        "📜 **История обращений**\n\n"
        "Закрытые тикеты:",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Просмотр конкретного тикета (по кнопке из списка)
@router.callback_query(lambda c: c.data.startswith("support_view_"))
async def support_view_ticket(callback: types.CallbackQuery, session: AsyncSession):
    ticket_id = int(callback.data.split("_")[2])
    telegram_id = callback.from_user.id
    
    ticket_result = await session.execute(
        select(SupportTicket).where(SupportTicket.id == ticket_id)
    )
    ticket = ticket_result.scalar_one_or_none()
    
    if not ticket or ticket.user_id != telegram_id:
        await callback.answer("❌ Тикет не найден", show_alert=True)
        return
    
    # Получаем все сообщения тикета
    messages_result = await session.execute(
        select(SupportMessage)
        .where(SupportMessage.ticket_id == ticket_id)
        .order_by(SupportMessage.created_at)
    )
    messages = messages_result.scalars().all()
    
    # Формируем текст переписки
    status_text = {
        'open': '🟢 Открыт',
        'in_progress': '🟡 В работе',
        'waiting_user': '🔴 Ожидает вас',
        'waiting_admin': '🟠 Ожидает поддержку',
        'closed': '⚫ Закрыт'
    }.get(ticket.status, ticket.status)
    
    chat_text = f"💬 **Тикет #{ticket.id}**\n"
    chat_text += f"Статус: {status_text}\n"
    if ticket.closed_at and ticket.status == 'closed':
        chat_text += f"Закрыт: {ticket.closed_at.strftime('%d.%m.%Y %H:%M')}\n"
    chat_text += "\n**Переписка:**\n"
    
    for msg in messages[-15:]:
        sender = "👤 Вы" if msg.sender_type == 'user' else "🛠️ Поддержка"
        time = msg.created_at.strftime('%d.%m.%Y %H:%M')
        chat_text += f"\n{sender} ({time}):\n{msg.message}\n"
    
    # Формируем клавиатуру
    builder = InlineKeyboardBuilder()
    
    if ticket.status != 'closed':
        if ticket.status == 'waiting_user':
            builder.button(text="✏️ Ответить", callback_data=f"support_reply_{ticket.id}")
        builder.button(text="✅ Закрыть тикет", callback_data=f"support_close_{ticket.id}")
    else:
        builder.button(text="📋 К истории", callback_data="support_history")
    
    builder.button(text="🔙 Назад", callback_data="support_my_tickets")
    builder.adjust(1)
    
    await callback.message.edit_text(
        chat_text,
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# ========== НОВЫЙ ОБРАБОТЧИК ДЛЯ КНОПКИ "ИСТОРИЯ" ИЗ УВЕДОМЛЕНИЯ ==========
@router.callback_query(lambda c: c.data.startswith("support_ticket_"))
async def support_ticket_history(callback: types.CallbackQuery, session: AsyncSession):
    """Просмотр истории конкретного тикета из уведомления"""
    ticket_id = int(callback.data.split("_")[2])
    telegram_id = callback.from_user.id
    
    # Получаем тикет
    ticket_result = await session.execute(
        select(SupportTicket).where(SupportTicket.id == ticket_id)
    )
    ticket = ticket_result.scalar_one_or_none()
    
    if not ticket or ticket.user_id != telegram_id:
        await callback.answer("❌ Тикет не найден", show_alert=True)
        return
    
    # Получаем все сообщения тикета
    messages_result = await session.execute(
        select(SupportMessage)
        .where(SupportMessage.ticket_id == ticket_id)
        .order_by(SupportMessage.created_at)
    )
    messages = messages_result.scalars().all()
    
    # Формируем текст переписки
    status_text = {
        'open': '🟢 Открыт',
        'in_progress': '🟡 В работе',
        'waiting_user': '🔴 Ожидает вас',
        'waiting_admin': '🟠 Ожидает поддержку',
        'closed': '⚫ Закрыт'
    }.get(ticket.status, ticket.status)
    
    chat_text = f"💬 **Тикет #{ticket.id}**\n"
    chat_text += f"Статус: {status_text}\n"
    if ticket.closed_at and ticket.status == 'closed':
        chat_text += f"Закрыт: {ticket.closed_at.strftime('%d.%m.%Y %H:%M')}\n"
    chat_text += "\n**Переписка:**\n"
    
    for msg in messages[-15:]:
        sender = "👤 Вы" if msg.sender_type == 'user' else "🛠️ Поддержка"
        time = msg.created_at.strftime('%d.%m.%Y %H:%M')
        chat_text += f"\n{sender} ({time}):\n{msg.message}\n"
    
    # Формируем клавиатуру
    builder = InlineKeyboardBuilder()
    
    if ticket.status != 'closed':
        if ticket.status == 'waiting_user':
            builder.button(text="✏️ Ответить", callback_data=f"support_reply_{ticket.id}")
        builder.button(text="✅ Закрыть тикет", callback_data=f"support_close_{ticket.id}")
    
    builder.button(text="🔙 К списку", callback_data="support_my_tickets")
    builder.adjust(1)
    
    await callback.message.edit_text(
        chat_text,
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Ответ на тикет
@router.callback_query(lambda c: c.data.startswith("support_reply_"))
async def support_reply(callback: types.CallbackQuery, session: AsyncSession):
    ticket_id = int(callback.data.split("_")[2])
    
    ticket_result = await session.execute(
        select(SupportTicket).where(SupportTicket.id == ticket_id)
    )
    ticket = ticket_result.scalar_one()
    
    ticket.status = 'waiting_admin'
    await session.commit()
    
    await callback.message.edit_text(
        f"✏️ **Ответ на тикет #{ticket_id}**\n\n"
        "Напиши свой ответ одним сообщением:",
        parse_mode="Markdown"
    )
    await callback.answer()

# Закрытие тикета пользователем
@router.callback_query(lambda c: c.data.startswith("support_close_"))
async def support_close(callback: types.CallbackQuery, session: AsyncSession):
    ticket_id = int(callback.data.split("_")[2])
    telegram_id = callback.from_user.id
    
    ticket_result = await session.execute(
        select(SupportTicket).where(SupportTicket.id == ticket_id)
    )
    ticket = ticket_result.scalar_one()
    
    ticket.status = 'closed'
    ticket.closed_at = datetime.now()
    ticket.closed_by = 'user'
    await session.commit()
    
    await callback.message.edit_text(
        f"✅ **Тикет #{ticket_id} закрыт**\n\n"
        "Спасибо за обращение! Если возникнут новые вопросы — "
        "ты всегда можешь создать новое обращение через /support",
        parse_mode="Markdown"
    )
    await callback.answer()

# Назад к меню поддержки
@router.callback_query(lambda c: c.data == "support_back")
async def support_back(callback: types.CallbackQuery, session: AsyncSession):
    await callback.message.delete()
    await cmd_support(callback.message, session)
    await callback.answer()

# Функция для отправки уведомления пользователю от админа (используется из admin.py)
async def notify_user_new_message(bot, user_id: int, message: str, ticket_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Ответить", callback_data=f"support_reply_{ticket_id}")
    builder.button(text="📋 История", callback_data=f"support_ticket_{ticket_id}")
    builder.button(text="✅ Закрыть тикет", callback_data=f"support_close_{ticket_id}")
    builder.adjust(1)
    
    try:
        await bot.send_message(
            user_id,
            f"📬 **Новый ответ от поддержки**\n\n"
            f"{message}\n\n"
            f"<i>Тикет #{ticket_id}</i>",
            parse_mode="Markdown",
            reply_markup=builder.as_markup()
        )
        return True
    except Exception as e:
        print(f"Ошибка отправки уведомления пользователю: {e}")
        return False