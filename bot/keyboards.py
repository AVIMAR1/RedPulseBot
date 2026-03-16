from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
import os

# Константа для бонуса
REFERRAL_BONUS = 50

# URL Mini App из переменных окружения
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-bot-name.t.me")


def menu_root():
    """Основное меню бота - упрощённое (только поддержка, профиль, Mini App)"""
    builder = ReplyKeyboardBuilder()
    # Кнопка открытия Mini App
    builder.row(
        KeyboardButton(text="🎮 Red Pulse Game", web_app=WebAppInfo(url=WEBAPP_URL))
    )
    builder.row(
        KeyboardButton(text="👤 Профиль"),
        KeyboardButton(text="🆘 Поддержка"),
    )
    builder.row(
        KeyboardButton(text="📢 Анонсы"),
        KeyboardButton(text="📋 Задания"),
    )
    return builder.as_markup(resize_keyboard=True)


def main_menu():
    return menu_root()


def tasks_menu():
    """Меню для заданий"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📋 Доступные задания", callback_data="tasks_available"),
        InlineKeyboardButton(text="✅ Мои задания", callback_data="tasks_my")
    )
    builder.row(
        InlineKeyboardButton(text="🔄 Обновить", callback_data="tasks_refresh")
    )
    return builder.as_markup()


def shop_menu():
    """Меню магазина"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📦 Кейсы", callback_data="shop_cases"),
        InlineKeyboardButton(text="🚀 Бусты", callback_data="shop_boosts")
    )
    builder.row(
        InlineKeyboardButton(text="🎨 Скины", callback_data="shop_skins"),
        InlineKeyboardButton(text="🖼️ Аватарки", callback_data="shop_avatars")
    )
    return builder.as_markup()


def rating_menu():
    """Меню рейтинга"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🏆 Топ-10 по звёздам", callback_data="rating_stars"),
        InlineKeyboardButton(text="👆 Топ-10 по кликам", callback_data="rating_clicks")
    )
    return builder.as_markup()


def support_menu():
    """Меню поддержки"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Новое обращение", callback_data="support_new")
    builder.button(text="📋 Мои обращения", callback_data="support_my_tickets")
    builder.adjust(1)
    return builder.as_markup()


def announcements_menu():
    """Меню анонсов"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📰 Последние анонсы", callback_data="announcements_list")
    builder.button(text="🔔 Подписаться на уведомления", callback_data="announcements_subscribe")
    builder.adjust(1)
    return builder.as_markup()
