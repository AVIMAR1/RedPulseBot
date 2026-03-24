"""
Синхронизация данных между Mini App (Ферма) и основным ботом
"""
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from models import User
import json
import logging

logger = logging.getLogger(__name__)


class FarmDataSync:
    """Класс для синхронизации данных фермы с базой данных"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def sync_user_data(self, telegram_id: int, farm_data: dict):
        """
        Синхронизирует данные из фермы с базой данных
        
        farm_data ожидает:
        {
            'coins': int,          # монеты
            'crystals': int,       # кристаллы
            'stars': int,          # звезды
            'level': int,          # уровень фермы
            'xp': int,             # опыт
            'totalTaps': int,      # всего тапов
            'chargePower': float,  # сила заряда
            'fieldRows': int,      # количество рядов поля
            'blocksCount': int,    # количество блоков
            'reactionsCount': int  # количество реакций
        }
        """
        try:
            result = await self.session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                logger.warning(f"User {telegram_id} not found for sync")
                return False
            
            # Обновляем валюты
            if 'coins' in farm_data:
                user.click_coins = farm_data['coins']
            if 'crystals' in farm_data:
                user.crystals = farm_data['crystals']
            if 'stars' in farm_data:
                user.stars = farm_data['stars']
            
            # Обновляем прогресс
            if 'level' in farm_data:
                user.level = farm_data['level']
            if 'xp' in farm_data:
                user.xp = farm_data['xp']
            
            # Обновляем статистику
            if 'totalTaps' in farm_data:
                user.total_clicks = farm_data['totalTaps']
            if 'chargePower' in farm_data:
                user.click_power = int(farm_data['chargePower'])
            
            await self.session.commit()
            logger.info(f"Synced farm data for user {telegram_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error syncing farm data for {telegram_id}: {e}")
            await self.session.rollback()
            return False
    
    async def get_user_farm_data(self, telegram_id: int) -> dict:
        """Получает данные фермы пользователя из БД"""
        try:
            result = await self.session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                return self._get_default_farm_data()
            
            return {
                'reactor_level': user.level,
                'total_energy': user.total_clicks,
                'blocks_placed': getattr(user, 'blocks_placed', 0),
                'reactions_triggered': getattr(user, 'reactions_triggered', 0),
                'coins': user.click_coins,
                'crystals': user.crystals,
                'stars': user.stars,
                'xp': user.xp,
                'click_power': user.click_power
            }
            
        except Exception as e:
            logger.error(f"Error getting farm data for {telegram_id}: {e}")
            return self._get_default_farm_data()
    
    def _get_default_farm_data(self) -> dict:
        """Возвращает данные фермы по умолчанию"""
        return {
            'reactor_level': 1,
            'total_energy': 0,
            'blocks_placed': 0,
            'reactions_triggered': 0,
            'coins': 0,
            'crystals': 0,
            'stars': 0,
            'xp': 0,
            'click_power': 1
        }


# API эндпоинт для сохранения данных из Mini App
async def save_farm_data(telegram_id: int, farm_data: dict, session: AsyncSession):
    """
    Сохраняет данные из фермы в базу данных
    
    Вызывается из webapp_routes.py при сохранении в Mini App
    """
    sync = FarmDataSync(session)
    return await sync.sync_user_data(telegram_id, farm_data)


# API эндпоинт для получения данных фермы
async def get_farm_data(telegram_id: int, session: AsyncSession) -> dict:
    """
    Получает данные фермы из базы данных
    
    Вызывается при загрузке Mini App
    """
    sync = FarmDataSync(session)
    return await sync.get_user_farm_data(telegram_id)
