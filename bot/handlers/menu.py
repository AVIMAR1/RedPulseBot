# -*- coding: utf-8 -*-
from aiogram import Router, types

from bot.keyboards import menu_root, menu_games, menu_economy, menu_social, menu_services

router = Router()


@router.message(lambda m: m.text and m.text.strip() == "🏠 Меню")
async def back_to_root(message: types.Message):
    await message.answer("🏠 Главное меню:", reply_markup=menu_root())


@router.message(lambda m: m.text and m.text.strip() == "🎮 Игры")
async def open_games(message: types.Message):
    await message.answer("🎮 Раздел: игры", reply_markup=menu_games())


@router.message(lambda m: m.text and m.text.strip() == "💰 Экономика")
async def open_economy(message: types.Message):
    await message.answer("💰 Раздел: экономика", reply_markup=menu_economy())


@router.message(lambda m: m.text and m.text.strip() == "👥 Соц")
async def open_social(message: types.Message):
    await message.answer("👥 Раздел: социальное", reply_markup=menu_social())


@router.message(lambda m: m.text and m.text.strip() == "🛠 Сервисы")
async def open_services(message: types.Message):
    await message.answer("🛠 Раздел: сервисы", reply_markup=menu_services())

