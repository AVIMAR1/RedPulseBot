from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models import User, Task, UserTask
from bot.keyboards import tasks_menu, WEBAPP_URL

router = Router()


@router.message(lambda message: message.text == "📋 Задания")
@router.message(Command("tasks"))
async def cmd_tasks(message: types.Message, session: AsyncSession):
    telegram_id = message.from_user.id

    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    if not user:
        await message.answer("❌ Сначала введите /start")
        return

    # Получаем активные задания
    tasks_result = await session.execute(select(Task).where(Task.is_active == True))
    tasks = tasks_result.scalars().all()

    if not tasks:
        await message.answer(
            "📋 **Задания**\n\n"
            "Пока нет доступных заданий. Загляни позже!\n\n"
            "🎮 Все задания доступны в Mini App!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎮 Открыть Mini App", web_app=WebAppInfo(url=WEBAPP_URL))]
            ])
        )
        return

    # Проверяем выполненные
    completed = set()
    for task in tasks:
        user_task = await session.execute(
            select(UserTask).where(
                and_(UserTask.user_id == telegram_id, UserTask.task_id == task.id)
            )
        )
        if user_task.scalar_one_or_none():
            completed.add(task.id)

    available_count = len(tasks) - len(completed)

    # Формируем текст
    tasks_text = "📋 **Доступные задания**\n\n"
    tasks_text += f"Всего: {len(tasks)} | Доступно: {available_count}\n\n"

    for task in tasks[:5]:  # Показываем первые 5
        reward = []
        if task.reward_coins:
            reward.append(f"{task.reward_coins} 🪙")
        if task.reward_stars:
            reward.append(f"{task.reward_stars} ⭐")
        
        status = "✅" if task.id in completed else "⬜"
        tasks_text += f"{status} **{task.title}** — {', '.join(reward) if reward else 'Нет награды'}\n"

    if len(tasks) > 5:
        tasks_text += f"\n... и ещё {len(tasks) - 5} заданий"

    tasks_text += "\n\n🎮 **Выполняй задания в Mini App!**"

    await message.answer(
        tasks_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎮 Выполнить задания", web_app=WebAppInfo(url=WEBAPP_URL))],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="tasks_refresh")]
        ])
    )


@router.callback_query(lambda c: c.data == "tasks_refresh")
async def tasks_refresh(callback: types.CallbackQuery, session: AsyncSession):
    await callback.message.delete()
    await cmd_tasks(callback.message, session)
    await callback.answer()


@router.callback_query(lambda c: c.data == "tasks_available")
async def tasks_available(callback: types.CallbackQuery, session: AsyncSession):
    await callback.answer("Открой Mini App для выполнения заданий!", show_alert=True)


@router.callback_query(lambda c: c.data == "tasks_my")
async def tasks_my(callback: types.CallbackQuery, session: AsyncSession):
    await callback.answer("История заданий доступна в Mini App!", show_alert=True)
