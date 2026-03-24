# 🔄 Обновление RedPulse Bot - Ферма (Реактор)

## 📋 Список изменений

### ✅ Исправления багов
1. **Снаряды больше не замедляются при прокрутке** - использован `performance.now()` для независимости от FPS
2. **Улучшено мигание температуры** - более заметная анимация при критическом уровне (0.4s вместо 0.8s)
3. **Увеличены иконки на блоках** - 32px вместо 18px, уровень 13px вместо 9px
4. **Анимация баланса** - теперь с анимацией только при выходе с фермы

### 🎨 Изменения интерфейса
1. **Поле 7x7** - исправлен размер поля
2. **Точка выпуска из центра** - 4-й блок (индекс 3)
3. **Надпись "Реактор"** - вместо "Поле"
4. **Большие иконки** - все элементы увеличены

### 📊 Обновление профиля
1. **Новая статистика фермы** в профиле Telegram:
   - Уровень реактора
   - Всего энергии
   - Блоков установлено
   - Реакций запущено

2. **Обновлённая админка** - добавлена секция "Ферма (Реактор)"

### 🔄 Синхронизация данных
1. **Новый модуль `core/farm_sync.py`** - синхронизация между Mini App и ботом
2. **Новые поля в модели User**:
   - `blocks_placed` - количество установленных блоков
   - `reactions_triggered` - количество запущенных реакций
   - `reactor_level` - уровень реактора
   - `total_energy_produced` - всего произведено энергии

---

## 🚀 Установка обновлений

### 1. Обновление базы данных

Выполните SQL запрос для добавления новых полей:

```sql
-- Добавление полей статистики фермы
ALTER TABLE users ADD COLUMN blocks_placed INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN reactions_triggered INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN reactor_level INTEGER DEFAULT 1;
ALTER TABLE users ADD COLUMN total_energy_produced INTEGER DEFAULT 0;
```

### 2. Обновление файлов

Обновлённые файлы:
- `webapp/index.html` - исправления багов и оптимизация
- `webapp/pf_script.js` - исправление снарядов и синхронизация
- `webapp/pf_styles.css` - увеличенные иконки и мигание температуры
- `bot/handlers/profile.py` - обновлённый профиль
- `models.py` - новые поля
- `templates/admin.html` - статистика фермы в админке
- `core/farm_sync.py` - новый файл синхронизации

### 3. Перезапуск бота

```bash
# Остановка бота
pm2 stop redpulse-bot

# Обновление кода (если через git)
git pull

# Установка зависимостей (если добавлены новые)
pip install -r requirements.txt

# Запуск бота
pm2 start redpulse-bot
pm2 logs redpulse-bot
```

---

## 🔧 Настройка синхронизации

### В webapp_routes.py добавьте:

```python
from core.farm_sync import save_farm_data, get_farm_data

@app.post("/api/farm/save")
async def api_save_farm_data(request: Request, session: AsyncSession = Depends(get_db)):
    """Сохранение данных фермы из Mini App"""
    data = await request.json()
    telegram_id = data.get('telegram_id')
    farm_data = data.get('farm_data', {})
    
    success = await save_farm_data(telegram_id, farm_data, session)
    return {"success": success}

@app.get("/api/farm/get/{telegram_id}")
async def api_get_farm_data(telegram_id: int, session: AsyncSession = Depends(get_db)):
    """Получение данных фермы для Mini App"""
    farm_data = await get_farm_data(telegram_id, session)
    return farm_data
```

### В pf_script.js добавьте при сохранении:

```javascript
// Отправка данных в бота для синхронизации
async function syncWithBot() {
    try {
        await fetch('/api/farm/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                telegram_id: userId,
                farm_data: {
                    coins: gameState.coins,
                    crystals: gameState.crystals,
                    stars: gameState.stars,
                    level: gameState.level,
                    xp: gameState.xp,
                    totalTaps: gameState.totalTaps,
                    chargePower: gameState.chargePower,
                    blocksCount: gameState.grid.flat().filter(b => b).length,
                    reactionsCount: gameState.reactionsTriggered || 0
                }
            })
        });
    } catch (e) {
        console.error('Sync error:', e);
    }
}

// Вызов при сохранении
function saveGame() {
    // ... существующий код ...
    syncWithBot(); // Добавить синхронизацию
}
```

---

## 📝 Проверка работы

1. Откройте Mini App - поле 7x7, надпись "Реактор"
2. Кликните на ядро - снаряд летит с постоянной скоростью
3. Нагрейте реактор - мигание температуры заметное
4. Проверьте профиль в Telegram - `/profile` или кнопка "Профиль"
5. Проверьте админку - `/admin` → просмотр пользователя → секция "Ферма"

---

## ⚠️ Возможные проблемы

### Баланс не синхронизируется
- Проверьте логи бота на ошибки синхронизации
- Убедитесь что `userId` в Mini App совпадает с `telegram_id`

### Поле всё ещё 9x10
- Очистите кэш браузера (Ctrl+F5)
- Проверьте версию файла (добавлен `?v=2` к CSS/JS)

### Новые поля в БД не появились
- Выполните SQL запрос вручную через SQLite Browser
- Или создайте миграцию через Alembic

---

## 📞 Поддержка

При возникновении проблем:
1. Проверьте логи: `pm2 logs redpulse-bot`
2. Проверьте консоль браузера (F12)
3. Убедитесь что все файлы обновлены
