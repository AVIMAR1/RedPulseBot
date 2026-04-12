// Telegram WebApp (используем глобальную переменную tg из index.html)
// Проверка что tg определён перед использованием
if (typeof tg !== 'undefined') {
    tg.ready();
    tg.expand();
} else {
    console.warn('pf_script.js: tg не определён, Telegram WebApp может не работать');
}

// ==========================================
// ЦЕНТРАЛИЗОВАННАЯ СИСТЕМА СИНХРОНИЗАЦИИ БАЛАНСА
// Принцип: баланс изменён → обновление → сохранение
// ==========================================

// Центральная функция обновления баланса - вызывает обновление UI и сохранение
function updateBalance() {
    if (typeof isSyncing !== 'undefined' && isSyncing) return;
    window.isSyncing = true;

    try {
        // Синхронизация gameState ↔ state
        syncGameState();

        // Обновление UI
        if (typeof updateUI === 'function') {
            updateUI();
        }

        // Сохранение
        if (typeof saveGame === 'function') {
            saveGame();
        }
    } catch (e) {
        console.error('Ошибка updateBalance:', e);
    }

    window.isSyncing = false;
}

// Синхронизация gameState и state (ДВУСТОРОННЯЯ)
function syncGameState() {
    if (typeof state === 'undefined' || typeof gameState === 'undefined') return;

    // ВАЖНО: НЕ перезаписываем gameState.coins из state!
    // gameState.coins — это основной баланс фермы (загружается из БД)
    // state.click_coins — это основной баланс меню (включает выведенные монеты)
    // Они должны быть равны, но syncGameState НЕ должен синхронизировать их напрямую
    // Синхронизация происходит через withdraw() и syncWithFarm()

    // state → gameState (только для кристаллов и звёзд — они НЕ используются в ферме)
    // gameState.coins = state.click_coins || 0;  // ← УБРАНО!
    gameState.crystals = state.crystals || 0;
    gameState.stars = state.stars || 0;
    gameState.totalTaps = state.total_clicks || 0;

    // gameState → state (XP, уровень и chargePower из gameState)
    state.level = gameState.level || 1;
    state.xp = gameState.xp || 0;
    state.xpToNext = gameState.xpToNext || 100;
    state.click_power = Math.floor(gameState.chargePower) || 1;

    // ВАЖНО: gameState.coins/crystals/stars → state (обратная синхронизация валюты)
    // Это нужно чтобы валюта заработанная в ферме попадала в главное состояние
    if (gameState.coins > (state.click_coins || 0)) {
        state.click_coins = gameState.coins;
    }
    if (gameState.crystals > (state.crystals || 0)) {
        state.crystals = gameState.crystals;
    }
    if (gameState.stars > (state.stars || 0)) {
        state.stars = gameState.stars;
    }
}

// Функции для изменения баланса (автоматически вызывают updateBalance)
function addCoins(amount, source = 'farm') {
    if (typeof state === 'undefined') return;
    state.click_coins = (state.click_coins || 0) + amount;
    updateBalance();
}

function addCrystals(amount, source = 'farm') {
    if (typeof state === 'undefined') return;
    state.crystals = (state.crystals || 0) + amount;
    updateBalance();
}

function addStars(amount, source = 'farm') {
    if (typeof state === 'undefined') return;
    state.stars = (state.stars || 0) + amount;
    updateBalance();
}

function spendCoins(amount) {
    if (typeof state === 'undefined') return false;
    if ((state.click_coins || 0) < amount) return false;
    state.click_coins -= amount;
    updateBalance();
    return true;
}

function spendCrystals(amount) {
    if (typeof state === 'undefined') return false;
    if ((state.crystals || 0) < amount) return false;
    state.crystals -= amount;
    updateBalance();
    return true;
}

function spendStars(amount) {
    if (typeof state === 'undefined') return false;
    if ((state.stars || 0) < amount) return false;
    state.stars -= amount;
    updateBalance();
    return true;
}

const CONFIG = {
    TEMP_PER_TAP: 15,
    TEMP_COOLDOWN_RATE: 0.4,
    TEMP_MAX_BASE: 100,
    TAP_COOLDOWN: 10000,
    BASE_CHARGE_POWER: 1,
    CHARGE_PER_LEVEL: 0.15,
    DROP_RATES: { COIN: 50, ROUTER: 25, MULTIPLIER: 10, DIAMOND: 10, STAR: 5 },
    MULTIPLIER_VALUES: [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0],
    MULTIPLIER_CHANCES: [35, 25, 18, 10, 6, 3, 2, 1],
    ROUTER_VALUES: [1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0],
    RARITY_PRICE_MULT: { COIN: 1.0, ROUTER: 1.2, MULTIPLIER: 1.3, DIAMOND: 1.4, STAR: 1.5 },
    PRICES: { BLOCK_BASE: 25, BLOCK_GROWTH: 1.25, BLOCK_ADD: 8, REROLL_BASE: 100, REROLL_GROWTH: 1.15, REROLL_ADD: 15, EXPAND_BASE: 2000, EXPAND_GROWTH: 1.35, EXPAND_ADD: 800 },
    XP: { BASE_PER_TAP: 10, BASE_PER_LEVEL: 100, GROWTH: 1.15, LEVEL_BONUS_CHARGE: 0.05, LEVEL_BONUS_TEMP: 10 },
    CONVERSION: { COIN: 1, DIAMOND: 3000, STAR: 50000 },
    SELL_BASE: 20,
    SELL_LEVEL_MULT: 1.5,
    LEVEL_BENEFITS: [
        { level: 1, benefit: 'Начало игры' },
        { level: 5, benefit: '+25% к температуре' },
        { level: 10, benefit: 'Открыт магазин' },
        { level: 15, benefit: '+50% к температуре' },
        { level: 20, benefit: 'x2 к XP' },
        { level: 25, benefit: '+75% к температуре' },
        { level: 30, benefit: 'Максимальный уровень!' }
    ]
};

const CELL_SIZE = 50;
const GAP = 4;
const FIELD_COLS = 7;
const FIELD_ROWS = 7;
const CHARGE_COL = 3;
const TEMP_PER_TAP = 15;
const TEMP_COOLDOWN_RATE = 0.4;
const TEMP_MAX_BASE = 100;
const MIN_TEMP_FOR_TAP = 10;
const MIN_COOLDOWN = 5000;
const MAX_COOLDOWN = 10000;
const MAX_DAMAGE_PER_HOUR = 3;
const CORE_BREAK_DURATION = 3600000;

const BLOCK_TYPES = { COIN: 'coin', DIAMOND: 'diamond', STAR: 'star', ROUTER: 'router', MULTIPLIER: 'multiplier' };
const ROUTER_TYPES = { DIRECTOR: 'director', MULTIPLIER: 'multi' };
const ROUTER_CONFIGS = [
    { type: ROUTER_TYPES.DIRECTOR, ports: ['top', 'right'] },
    { type: ROUTER_TYPES.DIRECTOR, ports: ['top', 'left'] },
    { type: ROUTER_TYPES.DIRECTOR, ports: ['bottom', 'right'] },
    { type: ROUTER_TYPES.DIRECTOR, ports: ['bottom', 'left'] },
    { type: ROUTER_TYPES.MULTIPLIER, ports: ['top', 'bottom', 'left'] },
    { type: ROUTER_TYPES.MULTIPLIER, ports: ['top', 'bottom', 'right'] },
    { type: ROUTER_TYPES.MULTIPLIER, ports: ['top', 'left', 'right'] },
    { type: ROUTER_TYPES.MULTIPLIER, ports: ['bottom', 'left', 'right'] },
    { type: ROUTER_TYPES.MULTIPLIER, ports: ['top', 'bottom', 'left', 'right'] }
];

function getLevelColorClass(level) {
    if (level >= 21) return 'block-level-21-23';
    if (level >= 18) return 'block-level-18-20';
    if (level >= 15) return 'block-level-15-17';
    if (level >= 12) return 'block-level-12-14';
    if (level >= 9) return 'block-level-9-11';
    if (level >= 6) return 'block-level-6-8';
    if (level >= 3) return 'block-level-3-5';
    return 'block-level-1-2';
}

let gameState = {
    coins: 0, crystals: 0, stars: 0,
    bankCoins: 0, bankCrystals: 0, bankStars: 0,
    level: 1, xp: 0, xpToNext: 100, temp: 0, maxTemp: 100, chargePower: 1,
    fieldRows: FIELD_ROWS, grid: [], selectedCell: null, shopItems: [],
    baseBlockPrice: CONFIG.PRICES.BLOCK_BASE, rerollCost: CONFIG.PRICES.REROLL_BASE, expandCost: CONFIG.PRICES.EXPAND_BASE,
    lastTapTime: 0, currentCooldown: 10000, isCharging: false,
    totalTaps: 0, totalEarned: 0, playTime: 0, firstPlay: true,
    damageTaken: 0, lastDamageReset: Date.now(), coreBrokenUntil: 0
};

function initGrid() {
    console.log('[initGrid] Создаём поле', gameState.fieldRows, 'x', FIELD_COLS);
    gameState.grid = [];
    for (let row = 0; row < gameState.fieldRows; row++) {
        gameState.grid[row] = [];
        for (let col = 0; col < FIELD_COLS; col++) {
            gameState.grid[row][col] = null;
        }
    }
    gameState.grid[0][CHARGE_COL] = createBlock(BLOCK_TYPES.COIN, 1, 1);
    console.log('[initGrid] Создан блок в строке 0, колонке', CHARGE_COL);
    generateShopItems();
}

function createBlock(type, level, value = 1) {
    const block = { type, level: level || 1, value: parseFloat(value) || 1, id: Date.now() + Math.random() };
    if (type === BLOCK_TYPES.ROUTER) {
        const randomConfig = ROUTER_CONFIGS[Math.floor(Math.random() * ROUTER_CONFIGS.length)];
        block.routerConfig = randomConfig;
        block.routerType = randomConfig.type;
        block.value = parseFloat((1.1 + (level - 1) * 0.1).toFixed(1));
    } else if (type === BLOCK_TYPES.MULTIPLIER) {
        block.value = parseFloat((1.5 + (level - 1) * 0.5).toFixed(1));
    } else if (type === BLOCK_TYPES.COIN || type === BLOCK_TYPES.DIAMOND || type === BLOCK_TYPES.STAR) {
        block.value = level;
    }
    return block;
}

function generateShopItems() {
    const shopLevel = Math.floor((gameState.level - 1) / 5) + 1;
    gameState.shopLevel = shopLevel;
    gameState.shopItems = [];
    for (let i = 0; i < 3; i++) {
        const maxLevel = shopLevel;
        const item = generateRandomBlock(maxLevel);
        const rarityMult = CONFIG.RARITY_PRICE_MULT[item.type.toUpperCase()] || 1.0;
        item.price = Math.floor(gameState.baseBlockPrice * Math.pow(1.5, item.level - 1) * rarityMult);
        gameState.shopItems.push(item);
    }
}

function generateRandomBlock(maxLevel = 3) {
    const rand = Math.random() * 100;
    let type = BLOCK_TYPES.COIN;
    let level = Math.floor(Math.random() * maxLevel) + 1;
    if (rand < CONFIG.DROP_RATES.STAR) type = BLOCK_TYPES.STAR;
    else if (rand < CONFIG.DROP_RATES.STAR + CONFIG.DROP_RATES.DIAMOND) type = BLOCK_TYPES.DIAMOND;
    else if (rand < CONFIG.DROP_RATES.STAR + CONFIG.DROP_RATES.DIAMOND + CONFIG.DROP_RATES.ROUTER) type = BLOCK_TYPES.ROUTER;
    else if (rand < CONFIG.DROP_RATES.STAR + CONFIG.DROP_RATES.DIAMOND + CONFIG.DROP_RATES.ROUTER + CONFIG.DROP_RATES.MULTIPLIER) type = BLOCK_TYPES.MULTIPLIER;
    return createBlock(type, level);
}

function getBlockIcon(block) {
    const icons = { [BLOCK_TYPES.COIN]: '🪙', [BLOCK_TYPES.DIAMOND]: '💎', [BLOCK_TYPES.STAR]: '⭐', [BLOCK_TYPES.ROUTER]: '🔀', [BLOCK_TYPES.MULTIPLIER]: '×' + block.value };
    return icons[block.type] || '❓';
}

function getBlockName(block) {
    const names = { [BLOCK_TYPES.COIN]: 'Монета', [BLOCK_TYPES.DIAMOND]: 'Алмаз', [BLOCK_TYPES.STAR]: 'Звезда', [BLOCK_TYPES.ROUTER]: 'Маршрутизатор', [BLOCK_TYPES.MULTIPLIER]: 'Множитель' };
    return names[block.type] || 'Блок';
}

function getBlockFullName(block) {
    const name = getBlockName(block);
    const levelStr = block.type === BLOCK_TYPES.MULTIPLIER || block.type === BLOCK_TYPES.ROUTER ? `x${block.value} Lvl${block.level}` : `Lvl${block.level}`;
    return `${name} ${levelStr}`;
}

function loadGame() {
    const saved = localStorage.getItem('pulseFarmSave_v2');
    // Принудительный сброс сохранения для обновления размера поля
    if (saved) {
        try {
            const data = JSON.parse(saved);
            // Проверяем если старое сохранение с неправильным размером поля
            if (data.fieldRows && data.fieldRows !== 7) {
                console.log('[LOAD] Старое сохранение с полем', data.fieldRows, 'строк. Сбрасываем...');
                localStorage.removeItem('pulseFarmSave_v2');
                initGrid();
                generateShopItems();
                gameState.firstPlay = true;
                return;
            }
        } catch (e) {
            console.error('Save corrupted, resetting...', e);
            localStorage.removeItem('pulseFarmSave_v2');
        }
    }
    
    if (saved) {
        try {
            const data = JSON.parse(saved);
            gameState = { ...gameState, ...data };
            // Исправляем загрузку XP - проверяем наличие свойства, а не значение
            if (data.xp === undefined) gameState.xp = 0;
            if (data.xpToNext === undefined) gameState.xpToNext = CONFIG.XP.BASE_PER_LEVEL;
            if (data.level === undefined) gameState.level = 1;
            // Принудительно устанавливаем размер поля 7x7
            gameState.fieldRows = 7;
            console.log('[LOAD] XP:', gameState.xp, '/', gameState.xpToNext, 'Level:', gameState.level, 'Field:', gameState.fieldRows, 'x', FIELD_COLS);
            if (!gameState.shopItems || gameState.shopItems.length === 0) generateShopItems();
            gameState.isCharging = false;
            if (!gameState.grid || gameState.grid.length === 0 || !gameState.grid[0]) {
                console.log('Grid missing, initializing...');
                initGrid();
            }
            // Синхронизация с главным state
            syncGameState();
        } catch (e) {
            console.error('Save corrupted, resetting...', e);
            initGrid();
            generateShopItems();
        }
    } else {
        initGrid();
        generateShopItems();
        showFirstTimeHelp();
        // Синхронизация с главным state
        syncGameState();
    }
    updateUI();
    // Ждём немного чтобы DOM точно загрузился
    setTimeout(() => {
        renderGrid();
    }, 100);
    startPassiveEffects();
}

function saveGame() {
    gameState.playTime = Math.floor((Date.now() - (gameState.lastSaveTime || Date.now())) / 1000) + (gameState.playTime || 0);
    gameState.lastSaveTime = Date.now();

    // Синхронизация с главным state
    syncGameState();

    localStorage.setItem('pulseFarmSave_v2', JSON.stringify(gameState));
    localStorage.setItem('redpulse_state', JSON.stringify(state));

    // Сохраняем банк фермы на сервер (click_coins НЕ отправляется - управляется через save-clicks)
    saveFarmStatsImmediate();
}

function updateUI() {
    // Обновление баланса фермы
    const coinsEl = document.getElementById('coins');
    const crystalsEl = document.getElementById('crystals');
    const starsEl = document.getElementById('stars');
    const bankCoinsEl = document.getElementById('bankCoins');
    const bankCrystalsEl = document.getElementById('bankCrystals');
    const bankStarsEl = document.getElementById('bankStars');

    if (coinsEl) coinsEl.textContent = (Math.floor(gameState.coins * 100) / 100).toFixed(2);
    if (crystalsEl) crystalsEl.textContent = formatNumber(gameState.crystals);
    if (starsEl) starsEl.textContent = (gameState.stars || 0).toFixed(2);
    if (bankCoinsEl) bankCoinsEl.textContent = (Math.floor((gameState.bankCoins || 0) * 100) / 100).toFixed(2);
    if (bankCrystalsEl) bankCrystalsEl.textContent = (Math.floor((gameState.bankCrystals || 0) * 10000) / 10000).toFixed(4);
    if (bankStarsEl) bankStarsEl.textContent = (gameState.bankStars || 0).toFixed(4);

    // Синхронизация с главным state для обновления баланса
    syncGameState();
    if (typeof updateMainBalance === 'function') {
        updateMainBalance();
    }

    const levelBadge = document.getElementById('levelBadge');
    const xpFill = document.getElementById('xpFill');
    const xpNext = document.getElementById('xpNext');
    if (levelBadge) levelBadge.textContent = gameState.level || 1;
    if (xpFill) xpFill.style.width = `${(gameState.xp / gameState.xpToNext) * 100}%`;
    if (xpNext) xpNext.textContent = formatNumber(gameState.xpToNext - gameState.xp);

    const shopLevelDisplay = document.getElementById('shopLevelDisplay');
    if (shopLevelDisplay) shopLevelDisplay.textContent = `(ур. ${gameState.shopLevel || 1})`;

    const tempText = document.getElementById('tempText');
    const tempFill = document.getElementById('tempFill');
    const currentTemp = gameState.temp || 0;
    const availableTemp = (gameState.maxTemp || 100) - currentTemp;
    const isTempCritical = availableTemp < TEMP_PER_TAP; // Меньше 15 = критично (нужно 15 для тапа)

    if (tempText) tempText.textContent = `${Math.floor(currentTemp)}/${gameState.maxTemp || 100}`;
    if (tempFill) {
        tempFill.style.width = `${(currentTemp / (gameState.maxTemp || 100)) * 100}%`;
    }
    
    // Мерцание всего блока температуры
    const tempBar = document.querySelector('.temp-bar');
    if (tempBar) {
        if (isTempCritical) {
            tempBar.classList.add('critical');
        } else {
            tempBar.classList.remove('critical');
        }
    }

    const coreStatus = document.getElementById('coreStatus');
    const coreStatusSub = document.getElementById('coreStatusSub');
    const coreStatusLabel = document.getElementById('coreStatusLabel');
    const fieldWrapper = document.querySelector('.field-wrapper');
    const isBroken = gameState.coreBrokenUntil > Date.now();

    if (isBroken) {
        fieldWrapper?.classList.add('field-broken');
        if (coreStatus) { coreStatus.textContent = 'СЛОМАНО'; coreStatus.style.color = '#e74c3c'; }

        // Show timer with seconds
        const remainingSec = Math.floor((gameState.coreBrokenUntil - Date.now()) / 1000);
        const mins = Math.floor(remainingSec / 60);
        const secs = remainingSec % 60;
        const timeStr = mins > 0 ? `${mins}м ${secs.toString().padStart(2, '0')}с` : `${secs}с`;
        if (coreStatusSub) coreStatusSub.textContent = timeStr;
        if (coreStatusLabel) coreStatusLabel.textContent = 'Состояние';
    } else {
        fieldWrapper?.classList.remove('field-broken');
        if (gameState.damageTaken > 0) {
            if (coreStatus) { coreStatus.textContent = `${gameState.damageTaken}/3`; coreStatus.style.color = '#f39c12'; }
            if (coreStatusSub) coreStatusSub.textContent = 'повреждений';
            if (coreStatusLabel) coreStatusLabel.textContent = 'Износ';
        } else {
            if (coreStatus) { coreStatus.textContent = 'OK'; coreStatus.style.color = '#27ae60'; }
            if (coreStatusSub) coreStatusSub.textContent = 'работает';
            if (coreStatusLabel) coreStatusLabel.textContent = 'Статус';
        }
    }

    document.getElementById('rerollCost').textContent = formatNumber(gameState.rerollCost || CONFIG.PRICES.REROLL_BASE);
    document.getElementById('expandCost').textContent = formatNumber(gameState.expandCost || CONFIG.PRICES.EXPAND_BASE);

    // Обновление силы ядра
    const corePowerEl = document.getElementById('corePower');
    if (corePowerEl) corePowerEl.textContent = `x${(gameState.chargePower || 1).toFixed(2)}`;

    const coreBtn = document.getElementById('coreBtn');
    const cooldownOverlay = document.getElementById('cooldownOverlay');
    const now = Date.now();
    const tapElapsed = now - (gameState.lastTapTime || 0);
    const remainingCooldown = gameState.currentCooldown - tapElapsed;

    if (remainingCooldown > 0) {
        const btnRemaining = Math.ceil(remainingCooldown / 1000);
        coreBtn?.classList.add('disabled');
        cooldownOverlay?.classList.remove('hidden');
        if (cooldownOverlay) cooldownOverlay.textContent = `${btnRemaining}с`;
    } else {
        coreBtn?.classList.remove('disabled');
        cooldownOverlay?.classList.add('hidden');
    }

    document.getElementById('rerollBtn').disabled = (gameState.coins || 0) < (gameState.rerollCost || CONFIG.PRICES.REROLL_BASE);
    document.getElementById('withdrawBtn').disabled = (gameState.bankCoins || 0) < 1 && (gameState.bankCrystals || 0) < 1 && (gameState.bankStars || 0) < 0.01;
    document.getElementById('sellBtn').disabled = !gameState.selectedCell;
    renderShopItems();
}

function renderShopItems() {
    const container = document.getElementById('shopItemsContainer');
    if (!container) return;
    container.innerHTML = '';
    gameState.shopItems.forEach((item, index) => {
        const itemEl = document.createElement('div');
        itemEl.className = 'shop-item';
        const levelClass = getLevelColorClass(item.level);
        let previewContent = '';
        if (item.type === BLOCK_TYPES.ROUTER) {
            const ports = item.routerConfig?.ports || [];
            previewContent = `<div style="position:relative;width:100%;height:100%;">${ports.map(p => `<div class="router-port-glow ${p}"></div>`).join('')}<span class="multiplier-value" style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);font-size:11px;">x${item.value}</span><span class="block-level-badge">${item.level}</span></div>`;
        } else if (item.type === BLOCK_TYPES.MULTIPLIER) {
            previewContent = `<span class="multiplier-value">x${item.value}</span><span class="block-level-badge">${item.level}</span>`;
        } else {
            previewContent = `${getBlockIcon(item)}<span class="block-level-badge">${item.level}</span>`;
        }
        itemEl.innerHTML = `
            <div class="shop-item-preview block ${levelClass}" style="display:flex;align-items:center;justify-content:center;font-size:24px;position:relative;">${previewContent}</div>
            <div class="shop-item-name">${getBlockFullName(item)}</div>
            <div class="shop-item-price">${item.price}🪙</div>
            <button class="shop-item-buy" onclick="buyShopItem(${index})" ${gameState.coins < item.price ? 'disabled' : ''}>Купить</button>
        `;
        container.appendChild(itemEl);
    });
}

function formatNumber(num) {
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num.toString();
}

function renderGrid() {
    const gridEl = document.getElementById('fieldGrid');
    if (!gridEl) {
        console.error('renderGrid: fieldGrid элемент не найден!');
        return;
    }
    console.log('[renderGrid] fieldRows:', gameState.fieldRows, 'FIELD_COLS:', FIELD_COLS);
    gridEl.innerHTML = '';

    const chargeIndicator = document.createElement('div');
    chargeIndicator.className = 'charge-start';
    const centerX = 10 + CHARGE_COL * (CELL_SIZE + GAP) + CELL_SIZE / 2;
    chargeIndicator.style.left = `${centerX}px`;
    chargeIndicator.innerHTML = '<div class="charge-start-arrow">▼</div>';
    gridEl.appendChild(chargeIndicator);

    for (let row = 0; row < gameState.fieldRows; row++) {
        for (let col = 0; col < FIELD_COLS; col++) {
            const cell = document.createElement('div');
            cell.className = 'cell';
            cell.dataset.row = row;
            cell.dataset.col = col;

            const block = gameState.grid[row][col];
            if (block) {
                const blockEl = document.createElement('div');
                const levelClass = getLevelColorClass(block.level);
                blockEl.className = `block ${levelClass}`;

                let blockContent = '';
                if (block.type === BLOCK_TYPES.ROUTER) {
                    if (block.routerConfig && block.routerConfig.ports) {
                        const ports = block.routerConfig.ports;
                        blockContent = `${ports.map(p => `<div class="router-port-glow ${p}"></div>`).join('')}<span class="multiplier-value">x${block.value}</span><span class="block-level-badge">${block.level}</span>`;
                    }
                } else if (block.type === BLOCK_TYPES.MULTIPLIER) {
                    blockContent = `<span class="multiplier-value">x${block.value}</span><span class="block-level-badge">${block.level}</span>`;
                } else {
                    blockContent = `<span class="block-icon">${getBlockIcon(block)}</span><span class="block-level-badge">${block.level}</span>`;
                }

                blockEl.innerHTML = blockContent;
                cell.appendChild(blockEl);

                if (gameState.selectedCell && gameState.selectedCell.row === row && gameState.selectedCell.col === col) {
                    cell.classList.add('selected');
                    cell.style.borderColor = '#f1c40f';
                    cell.style.boxShadow = '0 0 25px rgba(241, 196, 15, 0.5)';
                }
            } else {
                cell.classList.add('empty');
                if (gameState.selectedCell) {
                    cell.style.borderColor = '#27ae60';
                    cell.style.background = 'rgba(39, 174, 96, 0.15)';
                }
            }

            cell.addEventListener('click', (e) => onCellClick(e, row, col));
            gridEl.appendChild(cell);
        }
    }
}

function tapCore() {
    // Проверка что gameState определён
    if (typeof gameState === 'undefined') {
        console.error('tapCore: gameState не определён');
        return;
    }
    
    if (gameState.isCharging) return;

    const now = Date.now();

    // Check if core is broken - show timer with seconds
    if (gameState.coreBrokenUntil > now) {
        const remainingSec = Math.floor((gameState.coreBrokenUntil - now) / 1000);
        const mins = Math.floor(remainingSec / 60);
        const secs = remainingSec % 60;
        const timeStr = mins > 0 ? `${mins}м ${secs}с` : `${secs}с`;
        showToast(`Ядро сломано! Ещё ${timeStr}`, 'error');
        return;
    }

    // Reset damage counter every hour
    if (now - gameState.lastDamageReset > 3600000) {
        gameState.damageTaken = 0;
        gameState.lastDamageReset = now;
    }

    const timeSinceTap = now - gameState.lastTapTime;

    if (timeSinceTap < gameState.currentCooldown) {
        // Убрали уведомление о перезарядке
        return;
    }

    // Check temperature - show warning BEFORE damage
    const availableTemp = gameState.maxTemp - gameState.temp;
    if (availableTemp < MIN_TEMP_FOR_TAP) {
        // Show critical warning if this is the last warning
        const warningOverlay = document.getElementById('warningOverlay');
        const warningText = document.getElementById('warningText');

        if (gameState.damageTaken >= MAX_DAMAGE_PER_HOUR - 1) {
            // Last warning - critical
            warningOverlay.classList.add('critical');
            warningText.textContent = '⚠️ ПОСЛЕДНЕЕ ПРЕДУПРЕЖДЕНИЕ! СЛОМАЕТСЯ!';
        } else {
            warningOverlay.classList.remove('critical');
            warningText.textContent = `⚠️ ПЕРЕГРЕВ! Ещё ${MAX_DAMAGE_PER_HOUR - gameState.damageTaken - 1} предупрежд.`;
        }

        warningOverlay.classList.add('show');
        setTimeout(() => {
            warningOverlay.classList.remove('show');
            warningOverlay.classList.remove('critical');
        }, 3000);

        // Apply damage
        gameState.damageTaken++;

        // 5 second cooldown on overheat
        gameState.lastTapTime = now;
        gameState.currentCooldown = 5000;

        const coreBtn = document.getElementById('coreBtn');
        coreBtn.style.animation = 'core-overheat 0.5s ease-in-out';
        setTimeout(() => { coreBtn.style.animation = ''; }, 500);

        const fieldWrapper = document.querySelector('.field-wrapper');
        fieldWrapper?.classList.remove('field-damaged');
        void fieldWrapper?.offsetWidth;
        fieldWrapper?.classList.add('field-damaged');
        setTimeout(() => { fieldWrapper?.classList.remove('field-damaged'); }, 500);

        if (gameState.damageTaken >= MAX_DAMAGE_PER_HOUR) {
            gameState.coreBrokenUntil = now + CORE_BREAK_DURATION;
            showToast(`Ядро СЛОМАНО! 60м 00с`, 'error');
            fieldWrapper?.classList.add('field-broken');
            // Hide warning overlay
            warningOverlay.classList.remove('show');
        } else {
            showToast(`Перегрев! Блокировка на 5с`, 'error');
        }
        updateUI();
        return;
    }

    // Normal tap
    gameState.currentCooldown = Math.floor(Math.random() * (MAX_COOLDOWN - MIN_COOLDOWN + 1)) + MIN_COOLDOWN;
    gameState.lastTapTime = now;
    gameState.temp = Math.min(gameState.temp + TEMP_PER_TAP, gameState.maxTemp);
    gameState.isCharging = true;
    gameState.totalTaps++;

    launchCharge();
    addXP(CONFIG.XP.BASE_PER_TAP);

    if (tg.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');
}

function launchCharge() {
    const fieldGrid = document.getElementById('fieldGrid');
    if (!fieldGrid) { gameState.isCharging = false; return; }

    const padding = 10;
    const fieldWidth = FIELD_COLS * (CELL_SIZE + GAP) + padding * 2;
    const fieldHeight = gameState.fieldRows * (CELL_SIZE + GAP) + padding * 2;
    const speed = 2;

    let charge = gameState.chargePower || 1;
    let x = (CHARGE_COL + 0.5) * (CELL_SIZE + GAP) + padding;
    let y = padding - 10;
    let dir = { x: 0, y: 1 };

    const chargeEl = document.createElement('div');
    chargeEl.className = 'charge-particle';
    chargeEl.style.left = `${x - 9}px`;
    chargeEl.style.top = `${y - 9}px`;
    fieldGrid.appendChild(chargeEl);

    const processedBlocks = new Set();
    let lastTrail = 0;

    function move(timestamp) {
        if (!lastTrail) lastTrail = timestamp;

        x += dir.x * speed;
        y += dir.y * speed;

        if (timestamp - lastTrail > 100) {
            const trail = document.createElement('div');
            trail.className = 'charge-trail';
            trail.style.left = `${x - 4}px`;
            trail.style.top = `${y - 4}px`;
            fieldGrid.appendChild(trail);
            setTimeout(() => trail.remove(), 400);
            lastTrail = timestamp;
        }

        chargeEl.style.left = `${x - 9}px`;
        chargeEl.style.top = `${y - 9}px`;

        // Bounds check - include TOP boundary to prevent projectiles flying out
        if (x < padding - 10 || x > fieldWidth - padding + 10 || y < padding - 10 || y > fieldHeight - padding + 10) {
            // Убрали уведомления об уходе снаряда
            createExplosion(x, y, fieldGrid);
            setTimeout(() => { gameState.isCharging = false; updateUI(); saveGame(); }, 300);
            return;
        }

        // Block collision
        const col = Math.floor((x - padding) / (CELL_SIZE + GAP));
        const row = Math.floor((y - padding) / (CELL_SIZE + GAP));
        const blockKey = `${row}-${col}`;

        if (row >= 0 && row < gameState.fieldRows && col >= 0 && col < FIELD_COLS) {
            const block = gameState.grid[row][col];
            if (block && !processedBlocks.has(blockKey)) {
                const cellX = padding + col * (CELL_SIZE + GAP);
                const cellY = padding + row * (CELL_SIZE + GAP);
                const dist = Math.sqrt(Math.pow(x - (cellX + CELL_SIZE/2), 2) + Math.pow(y - (cellY + CELL_SIZE/2), 2));

                if (dist < CELL_SIZE / 2 - 2) {
                    processedBlocks.add(blockKey);
                    handleBlock(block, row, col, charge, dir, processedBlocks, chargeEl, x, y);
                    return;
                }
            }
        }

        requestAnimationFrame(move);
    }

    requestAnimationFrame(move);
}

function handleBlock(block, row, col, charge, dir, processed, chargeEl, x, y) {
    const padding = 10;
    const fieldGrid = document.getElementById('fieldGrid');
    const cellX = padding + col * (CELL_SIZE + GAP);
    const cellY = padding + row * (CELL_SIZE + GAP);

    chargeEl.remove();

    switch (block.type) {
        case BLOCK_TYPES.COIN:
            const coins = charge * CONFIG.CONVERSION.COIN * block.level;
            // Начисляем в банк фермы (не на основной баланс)
            gameState.bankCoins = (gameState.bankCoins || 0) + coins;
            gameState.totalEarned += coins;
            showFloatingEarn(row, col, `+${coins.toFixed(2)} 🪙`, 'coin');
            spawnCharge(x, y, dir, charge, processed, 5);
            updateBalance();
            break;

        case BLOCK_TYPES.DIAMOND:
            const diamonds = (charge * block.level) / CONFIG.CONVERSION.DIAMOND;
            // Начисляем в банк фермы (не на основной баланс)
            gameState.bankCrystals = (gameState.bankCrystals || 0) + diamonds;
            showFloatingEarn(row, col, `+${(Math.floor(diamonds * 10000) / 10000).toFixed(4)} 💎`, 'diamond');
            spawnCharge(x, y, dir, charge, processed, 5);
            updateBalance();
            break;

        case BLOCK_TYPES.STAR:
            const stars = (charge * block.level) / CONFIG.CONVERSION.STAR;
            // Начисляем в банк фермы (не на основной баланс)
            gameState.bankStars = (gameState.bankStars || 0) + stars;
            showFloatingEarn(row, col, `+${stars.toFixed(6)} ⭐`, 'star');
            spawnCharge(x, y, dir, charge, processed, 5);
            updateBalance();
            break;

        case BLOCK_TYPES.MULTIPLIER:
            const newCharge = charge * block.value;
            showFloatingEarn(row, col, `×${block.value}!`, 'multiplier');
            setTimeout(() => spawnCharge(cellX + CELL_SIZE/2, cellY + CELL_SIZE/2, dir, newCharge, processed, 8), 50);
            break;

        case BLOCK_TYPES.ROUTER:
            const hitPort = getHitPort(dir);
            if (!block.routerConfig || !block.routerConfig.ports) {
                setTimeout(finishCharging, 100);
                return;
            }

            const ports = block.routerConfig.ports;
            if (!ports.includes(hitPort)) {
                setTimeout(finishCharging, 100);
                return;
            }

            const boostedCharge = charge * block.value;
            showFloatingEarn(row, col, `🔀 x${block.value}!`, 'router');

            const outputPorts = ports.filter(p => p !== hitPort);
            if (outputPorts.length === 0) {
                setTimeout(finishCharging, 100);
                return;
            }

            const portToDir = {
                'top': { x: 0, y: -1 },
                'bottom': { x: 0, y: 1 },
                'left': { x: -1, y: 0 },
                'right': { x: 1, y: 0 }
            };

            const newProcessed = new Set(processed);
            newProcessed.add(`${row}-${col}`);

            outputPorts.forEach((port, i) => {
                const outDir = portToDir[port];
                const outX = cellX + CELL_SIZE/2 + outDir.x * (CELL_SIZE/2 + 3);
                const outY = cellY + CELL_SIZE/2 + outDir.y * (CELL_SIZE/2 + 3);
                setTimeout(() => spawnCharge(outX, outY, outDir, boostedCharge, newProcessed, 12), i * 80);
            });
            break;

        default:
            spawnCharge(x, y, dir, charge, processed, 5);
    }
}

function createExplosion(x, y, fieldGrid) {
    const explosion = document.createElement('div');
    explosion.className = 'explosion';
    explosion.style.left = `${x - 30}px`;
    explosion.style.top = `${y - 30}px`;
    fieldGrid.appendChild(explosion);

    // Create particles
    const colors = ['#e74c3c', '#f39c12', '#f1c40f', '#ffffff'];
    for (let i = 0; i < 8; i++) {
        const particle = document.createElement('div');
        particle.className = 'explosion-particle';
        particle.style.background = colors[Math.floor(Math.random() * colors.length)];
        particle.style.left = `${x - 4}px`;
        particle.style.top = `${y - 4}px`;

        const angle = (i / 8) * Math.PI * 2;
        const distance = 30 + Math.random() * 20;
        particle.style.setProperty('--tx', `${Math.cos(angle) * distance}px`);
        particle.style.setProperty('--ty', `${Math.sin(angle) * distance}px`);

        explosion.appendChild(particle);
    }

    setTimeout(() => explosion.remove(), 400);
}

function createBreedingAnimation(row, col, newLevel) {
    const gridEl = document.getElementById('fieldGrid');
    const padding = 10;
    const cellX = padding + col * (CELL_SIZE + GAP);
    const cellY = padding + row * (CELL_SIZE + GAP);

    // Add glow to cell
    const cell = gridEl.children[row * FIELD_COLS + col + 1]; // +1 for charge indicator
    if (cell) {
        cell.classList.add('breeding-glow');
        setTimeout(() => cell.classList.remove('breeding-glow'), 600);
    }

    // Show breeding text
    const breedText = document.createElement('div');
    breedText.className = 'breeding-text';
    breedText.textContent = `+${newLevel}!`;
    breedText.style.left = `${cellX + CELL_SIZE/2}px`;
    breedText.style.top = `${cellY + CELL_SIZE/2}px`;
    gridEl.appendChild(breedText);

    setTimeout(() => breedText.remove(), 800);
}

function spawnCharge(x, y, dir, charge, processed, skipFrames) {
    const fieldGrid = document.getElementById('fieldGrid');
    if (!fieldGrid) { finishCharging(); return; }

    const padding = 10;
    const fieldWidth = FIELD_COLS * (CELL_SIZE + GAP) + padding * 2;
    const fieldHeight = gameState.fieldRows * (CELL_SIZE + GAP) + padding * 2;
    const speed = 3; // Увеличили скорость для более плавного движения

    const chargeEl = document.createElement('div');
    chargeEl.className = 'charge-particle';
    chargeEl.style.left = `${x - 9}px`;
    chargeEl.style.top = `${y - 9}px`;
    fieldGrid.appendChild(chargeEl);

    let frames = 0;
    let lastTrail = 0;
    let lastTime = performance.now();

    function move() {
        const now = performance.now();
        const delta = now - lastTime;
        
        // Движение на основе delta time для независимости от FPS
        const moveDistance = speed * (delta / 16.67); // Нормализация к 60 FPS
        x += dir.x * moveDistance;
        y += dir.y * moveDistance;
        frames++;
        lastTime = now;

        if (frames < skipFrames) {
            chargeEl.style.left = `${x - 9}px`;
            chargeEl.style.top = `${y - 9}px`;
            if (now - lastTrail > 100) {
                const trail = document.createElement('div');
                trail.className = 'charge-trail';
                trail.style.left = `${x - 4}px`;
                trail.style.top = `${y - 4}px`;
                fieldGrid.appendChild(trail);
                setTimeout(() => trail.remove(), 400);
                lastTrail = now;
            }
            requestAnimationFrame(move);
            return;
        }

        if (now - lastTrail > 100) {
            const trail = document.createElement('div');
            trail.className = 'charge-trail';
            trail.style.left = `${x - 4}px`;
            trail.style.top = `${y - 4}px`;
            fieldGrid.appendChild(trail);
            setTimeout(() => trail.remove(), 400);
            lastTrail = now;
        }

        chargeEl.style.left = `${x - 9}px`;
        chargeEl.style.top = `${y - 9}px`;

        // Bounds check - include TOP boundary to prevent projectiles flying out
        if (x < padding - 10 || x > fieldWidth - padding + 10 || y < padding - 10 || y > fieldHeight - padding + 10) {
            // Убрали уведомления об уходе снаряда
            chargeEl.remove();
            setTimeout(finishCharging, 300);
            return;
        }

        const col = Math.floor((x - padding) / (CELL_SIZE + GAP));
        const row = Math.floor((y - padding) / (CELL_SIZE + GAP));
        const blockKey = `${row}-${col}`;

        if (row >= 0 && row < gameState.fieldRows && col >= 0 && col < FIELD_COLS) {
            const block = gameState.grid[row][col];
            if (block && !processed.has(blockKey)) {
                const cellX = padding + col * (CELL_SIZE + GAP);
                const cellY = padding + row * (CELL_SIZE + GAP);
                const dist = Math.sqrt(Math.pow(x - (cellX + CELL_SIZE/2), 2) + Math.pow(y - (cellY + CELL_SIZE/2), 2));

                if (dist < CELL_SIZE / 2 - 2) {
                    processed.add(blockKey);
                    handleBlock(block, row, col, charge, dir, processed, chargeEl, x, y);
                    return;
                }
            }
        }

        requestAnimationFrame(move);
    }

    requestAnimationFrame(move);
}

function getHitPort(dir) {
    if (dir.y > 0) return 'top';
    if (dir.y < 0) return 'bottom';
    if (dir.x > 0) return 'left';
    if (dir.x < 0) return 'right';
    return null;
}

function finishCharging() {
    setTimeout(() => {
        if (document.querySelectorAll('.charge-particle').length === 0) {
            gameState.isCharging = false;
            saveGame();
            updateUI();
        } else {
            finishCharging();
        }
    }, 300);
}

function addXP(amount) {
    const xpMultiplier = gameState.level >= 20 ? 2 : 1;
    const xpGained = amount * xpMultiplier;
    gameState.xp = (gameState.xp || 0) + xpGained;
    console.log('[XP] +'+xpGained+' XP, текущий: '+gameState.xp+'/'+gameState.xpToNext+', уровень: '+gameState.level);
    while (gameState.xp >= gameState.xpToNext) levelUp();
    updateBalance();
}

function levelUp() {
    const xpBefore = gameState.xp;
    gameState.xp -= gameState.xpToNext;
    gameState.level++;
    gameState.xpToNext = Math.round(CONFIG.XP.BASE_PER_LEVEL * Math.pow(CONFIG.XP.GROWTH, gameState.level - 1));
    const oldChargePower = gameState.chargePower;
    gameState.chargePower = CONFIG.BASE_CHARGE_POWER + (gameState.level - 1) * CONFIG.CHARGE_PER_LEVEL;
    const newChargePower = gameState.chargePower;
    gameState.maxTemp = CONFIG.TEMP_MAX_BASE + (gameState.level - 1) * CONFIG.XP.LEVEL_BONUS_TEMP;
    showToast(`🎉 Уровень ${gameState.level}!`, 'success');
    if (tg.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
    const benefit = CONFIG.LEVEL_BENEFITS.find(b => b.level === gameState.level);
    if (benefit) setTimeout(() => showToast(benefit.benefit, 'info'), 1000);
    // Показываем увеличение силы заряда
    const chargeDiff = (newChargePower - oldChargePower).toFixed(2);
    if (chargeDiff > 0) {
        setTimeout(() => showToast(`⚡ Сила ядра +${chargeDiff}!`, 'info'), 1500);
    }
}

function buyShopItem(index) {
    const item = gameState.shopItems[index];
    if (!item) return;

    if ((gameState.coins || 0) < item.price) {
        showToast('Недостаточно монет!', 'error');
        return;
    }

    let emptyCell = null;
    for (let row = 0; row < gameState.fieldRows; row++) {
        for (let col = 0; col < FIELD_COLS; col++) {
            if (!gameState.grid[row][col]) {
                emptyCell = { row, col };
                break;
            }
        }
        if (emptyCell) break;
    }

    if (!emptyCell) {
        showToast('Нет места!', 'error');
        return;
    }

    const newBlock = {
        type: item.type,
        level: item.level,
        value: item.value,
        routerConfig: item.routerConfig ? {...item.routerConfig} : null,
        routerType: item.routerType,
        id: Date.now() + Math.random()
    };

    gameState.grid[emptyCell.row][emptyCell.col] = newBlock;
    // Покупка за монеты из основного баланса
    state.click_coins -= item.price;
    gameState.baseBlockPrice = Math.floor(gameState.baseBlockPrice * 1.1);

    gameState.shopItems.forEach(i => {
        const rarityMult = CONFIG.RARITY_PRICE_MULT[i.type.toUpperCase()] || 1.0;
        i.price = Math.floor(gameState.baseBlockPrice * Math.pow(1.5, i.level - 1) * rarityMult);
    });

    const newMaxLevel = Math.floor((gameState.level - 1) / 5) + 1;
    const newItem = generateRandomBlock(newMaxLevel);
    const newRarityMult = CONFIG.RARITY_PRICE_MULT[newItem.type.toUpperCase()] || 1.0;
    newItem.price = Math.floor(gameState.baseBlockPrice * Math.pow(1.5, newItem.level - 1) * newRarityMult);
    gameState.shopItems[index] = newItem;

    showToast('Блок куплен! Цены +10%', 'success');
    if (tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
    updateBalance();
    renderGrid();
}

function rerollShop() {
    if ((state.click_coins || 0) < (gameState.rerollCost || CONFIG.PRICES.REROLL_BASE)) {
        showToast('Недостаточно монет!', 'error');
        return;
    }
    state.click_coins -= gameState.rerollCost;
    generateShopItems();
    gameState.rerollCost = Math.floor(gameState.rerollCost * CONFIG.PRICES.REROLL_GROWTH + CONFIG.PRICES.REROLL_ADD);
    showToast('Ассортимент обновлён!', 'success');
    updateBalance();
}

function expandField() {
    if ((state.click_coins || 0) < (gameState.expandCost || CONFIG.PRICES.EXPAND_BASE)) {
        showToast('Недостаточно монет!', 'error');
        return;
    }
    state.click_coins -= gameState.expandCost;
    gameState.fieldRows++;
    gameState.grid.push([]);
    for (let col = 0; col < FIELD_COLS; col++) {
        gameState.grid[gameState.fieldRows - 1][col] = null;
    }
    gameState.expandCost = Math.floor(gameState.expandCost * CONFIG.PRICES.EXPAND_GROWTH + CONFIG.PRICES.EXPAND_ADD);
    showToast('Поле расширено!', 'success');
    if (tg.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
    updateBalance();
    renderGrid();
}

function sellSelected() {
    if (!gameState.selectedCell) {
        showToast('Выберите блок!', 'warning');
        return;
    }
    const block = gameState.grid[gameState.selectedCell.row][gameState.selectedCell.col];
    if (!block) {
        showToast('Здесь пусто!', 'error');
        return;
    }
    if (block.type === BLOCK_TYPES.COIN) {
        let coinCount = 0;
        for (let row = 0; row < gameState.fieldRows; row++) {
            for (let col = 0; col < FIELD_COLS; col++) {
                if (gameState.grid[row][col]?.type === BLOCK_TYPES.COIN) coinCount++;
            }
        }
        if (coinCount <= 1) {
            showToast('Нельзя продать последний блок монеты!', 'error');
            return;
        }
    }
    const sellPrice = Math.floor(CONFIG.SELL_BASE * Math.pow(CONFIG.SELL_LEVEL_MULT, block.level - 1));
    // Продажа за монеты на основной баланс
    state.click_coins = (state.click_coins || 0) + sellPrice;
    gameState.grid[gameState.selectedCell.row][gameState.selectedCell.col] = null;
    gameState.selectedCell = null;
    showToast(`+${sellPrice} 🪙`, 'success');
    if (tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
    updateBalance();
    renderGrid();
}

function withdraw() {
    let withdrawn = false;
    if ((gameState.bankCoins || 0) >= 1) {
        const amount = Math.floor(gameState.bankCoins);
        gameState.bankCoins -= amount;
        state.click_coins = (state.click_coins || 0) + amount;
        withdrawn = true;
    }
    if ((gameState.bankCrystals || 0) >= 1) {
        const amount = Math.floor(gameState.bankCrystals);
        gameState.bankCrystals -= amount;
        state.crystals = (state.crystals || 0) + amount;
        withdrawn = true;
    }
    if ((gameState.bankStars || 0) >= 0.01) {
        const amount = Math.floor(gameState.bankStars * 100) / 100;
        gameState.bankStars -= amount;
        state.stars = (state.stars || 0) + amount;
        withdrawn = true;
    }
    if (withdrawn) {
        showToast('Выведено!', 'success');
        if (tg.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');

        // Синхронизируем gameState с обновлённым state
        gameState.coins = state.click_coins || 0;
        gameState.crystals = state.crystals || 0;
        gameState.stars = state.stars || 0;

        // Сохраняем state в localStorage
        localStorage.setItem('redpulse_state', JSON.stringify(state));

        // Синхронизация и сохранение в БД
        syncGameState();
        saveGame();
        updateUI();
        
        // НЕМЕДЛЕННОЕ сохранение в БД после вывода
        saveFarmStatsImmediate();
    } else {
        showToast('Минимум: 1🪙, 1💎 или 0.01⭐', 'warning');
    }
}

// Функция для немедленного сохранения валюты в БД (после вывода из банка)
async function saveFarmStatsImmediate() {
    if (typeof userId === 'undefined' || !userId) {
        console.warn('[saveFarmStatsImmediate] userId не определён!');
        return;
    }

    try {
        syncGameState();
        
        const farmStats = {
            userId: userId,
            reactor_level: gameState.reactor_level || 1,
            blocks_placed: gameState.blocks_placed || 0,
            reactions_triggered: gameState.totalTaps || 0,
            total_energy_produced: gameState.totalEarned || 0,
            // ВАЖНО: НЕ отправляем click_coins/stars/crystals — они управляются через save-clicks
            // Отправляем ТОЛЬКО банк фермы
            bank_coins: Math.floor(gameState.bankCoins || 0),
            bank_stars: Math.floor(gameState.bankStars || 0),
            bank_crystals: Math.floor(gameState.bankCrystals || 0)
        };

        console.log('[saveFarmStatsImmediate] Сохранение в БД:', farmStats);

        const response = await fetch('/api/save-farm-stats', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(farmStats)
        });

        if (response.ok) {
            const result = await response.json();
            console.log('[saveFarmStatsImmediate] УСПЕХ:', result);
        } else {
            console.error('[saveFarmStatsImmediate] Ошибка HTTP:', response.status);
        }
    } catch (e) {
        console.error('[saveFarmStatsImmediate] Ошибка:', e);
    }
}

let selectedForMove = null;

function onCellClick(e, row, col) {
    const block = gameState.grid[row][col];

    if (selectedForMove) {
        if (selectedForMove.row === row && selectedForMove.col === col) {
            selectedForMove = null;
            gameState.selectedCell = null;
            renderGrid();
            updateUI();
            return;
        }

        if (!block) {
            const sourceBlock = gameState.grid[selectedForMove.row][selectedForMove.col];
            gameState.grid[selectedForMove.row][selectedForMove.col] = null;
            gameState.grid[row][col] = sourceBlock;
            showToast('Блок перемещён', 'success');
            selectedForMove = null;
            gameState.selectedCell = null;
            saveGame();
            renderGrid();
            updateUI();
            return;
        }

        const sourceBlock = gameState.grid[selectedForMove.row][selectedForMove.col];
        if (sourceBlock && sourceBlock.type === block.type) {
            if (sourceBlock.type === BLOCK_TYPES.ROUTER && block.type === BLOCK_TYPES.ROUTER) {
                const sameLevel = sourceBlock.level === block.level;
                const sameValue = sourceBlock.value === block.value;
                const sourcePorts = sourceBlock.routerConfig?.ports?.sort().join(',') || '';
                const targetPorts = block.routerConfig?.ports?.sort().join(',') || '';
                const samePorts = sourcePorts === targetPorts;

                if (sameLevel && sameValue && samePorts) {
                    const newLevel = block.level + 1;
                    block.level = newLevel;
                    block.value = parseFloat((1.1 + (newLevel - 1) * 0.1).toFixed(1));
                    gameState.grid[selectedForMove.row][selectedForMove.col] = null;
                    createBreedingAnimation(row, col, newLevel);
                    showToast(`Скрещивание! Маршрутизатор ур. ${newLevel} (x${block.value})!`, 'success');
                    selectedForMove = null;
                    gameState.selectedCell = null;
                    saveGame();
                    renderGrid();
                    updateUI();
                    return;
                } else {
                    if (!samePorts) showToast('Порты не совпадают!', 'error');
                    else if (!sameLevel) showToast('Уровни не совпадают!', 'error');
                    selectedForMove = null;
                    gameState.selectedCell = null;
                    renderGrid();
                    updateUI();
                    return;
                }
            } else if (sourceBlock.value === block.value && sourceBlock.type !== BLOCK_TYPES.COIN && sourceBlock.type !== BLOCK_TYPES.DIAMOND && sourceBlock.type !== BLOCK_TYPES.STAR) {
                const newLevel = block.level + 1;
                block.level = newLevel;
                if (block.type === BLOCK_TYPES.ROUTER) block.value = parseFloat((1.1 + (newLevel - 1) * 0.1).toFixed(1));
                else if (block.type === BLOCK_TYPES.MULTIPLIER) block.value = parseFloat((1.5 + (newLevel - 1) * 0.5).toFixed(1));
                gameState.grid[selectedForMove.row][selectedForMove.col] = null;
                createBreedingAnimation(row, col, newLevel);
                showToast(`Скрещивание! Уровень ${newLevel}!`, 'success');
                selectedForMove = null;
                gameState.selectedCell = null;
                saveGame();
                renderGrid();
                updateUI();
                return;
            } else if ((sourceBlock.type === BLOCK_TYPES.COIN || sourceBlock.type === BLOCK_TYPES.DIAMOND || sourceBlock.type === BLOCK_TYPES.STAR) && sourceBlock.level === block.level) {
                const newLevel = block.level + 1;
                block.level = newLevel;
                block.value = newLevel;
                gameState.grid[selectedForMove.row][selectedForMove.col] = null;
                createBreedingAnimation(row, col, newLevel);
                showToast(`Скрещивание! Уровень ${newLevel}!`, 'success');
                selectedForMove = null;
                gameState.selectedCell = null;
                saveGame();
                renderGrid();
                updateUI();
                return;
            }
        }

        showToast('Нельзя скрестить/переместить', 'error');
        selectedForMove = null;
        gameState.selectedCell = null;
        renderGrid();
        updateUI();
        return;
    }

    if (block) {
        selectedForMove = { row, col };
        gameState.selectedCell = { row, col };
        renderGrid();
        updateUI();
        showToast('Выбрано! Перемести или продай', 'info');
    }
}

function startPassiveEffects() {
    // Temperature cooldown
    setInterval(() => {
        if (gameState.temp > 0) {
            const cooldownRate = CONFIG.TEMP_COOLDOWN_RATE * (1 + (gameState.level - 1) * 0.05);
            gameState.temp = Math.max(0, gameState.temp - cooldownRate);
            updateUI();
            saveGame();
        }
    }, 1000);

    // Update broken core timer every second
    setInterval(() => {
        if (gameState.coreBrokenUntil > Date.now()) {
            const coreStatusSub = document.getElementById('coreStatusSub');
            const remainingSec = Math.floor((gameState.coreBrokenUntil - Date.now()) / 1000);
            const mins = Math.floor(remainingSec / 60);
            const secs = remainingSec % 60;
            const timeStr = mins > 0 ? `${mins}м ${secs.toString().padStart(2, '0')}с` : `${secs}с`;
            if (coreStatusSub) coreStatusSub.textContent = timeStr;
        }
    }, 1000);

    // Auto-save to localStorage
    setInterval(() => { saveGame(); }, 15000);
    
    // Auto-save to DB every 30 seconds
    setInterval(() => { 
        if (userId && typeof userId !== 'undefined') {
            console.log('[AutoSave] Сохранение в БД...');
            saveFarmStats();
            saveFarmState();
        }
    }, 30000);
}

function showFirstTimeHelp() {
    const helpContent = `<strong>🔥 RedPulse Farm!</strong><br><br>Здесь энергия ядра превращается в богатство. Запускайте заряды, чтобы активировать блоки на ферме и зарабатывать монеты, алмазы и звезды.<br><br><strong>⚙️ КАК ЭТО РАБОТАЕТ:</strong><br>Устанавливайте блоки с умом:<br>💰 Блоки валют — приносят доход.<br>🔄 Маршрутизатор — принимает импульс и отправляет его дальше, преумножая мощность.<br>⚡ Бустер — усиливает заряд.<br><br>🔄 Скрещивание: Повышайте уровень блоков, чтобы увеличить награду.<br><br><strong>⚠️ ВНИМАНИЕ: КОНТРОЛЬ ТЕМПЕРАТУРЫ!</strong><br>Каждый выстрел нагревает ядро на 15 градусов. Если перегреть систему, ядро начнет разрушаться. Три аварии — и ядро встанет на 1 час. Следите за датчиками!<br><br><strong>📅 О СЕЗОНАХ:</strong><br>После окончания сезона монеты и звезды сгорают, но алмазы остаются у вас навсегда.`;
    document.getElementById('helpBody').innerHTML = helpContent;
    document.getElementById('helpModal').classList.add('active');
}

function showHelp() {
    const helpContent = `<strong>🔥 RedPulse Farm!</strong><br><br>Здесь энергия ядра превращается в богатство. Запускайте заряды, чтобы активировать блоки на ферме и зарабатывать монеты, алмазы и звезды.<br><br><strong>⚙️ КАК ЭТО РАБОТАЕТ:</strong><br>Устанавливайте блоки с умом:<br>💰 Блоки валют — приносят доход.<br>🔄 Маршрутизатор — принимает импульс и отправляет его дальше, преумножая мощность.<br>⚡ Бустер — усиливает заряд.<br><br>🔄 Скрещивание: Повышайте уровень блоков, чтобы увеличить награду.<br><br><strong>⚠️ ВНИМАНИЕ: КОНТРОЛЬ ТЕМПЕРАТУРЫ!</strong><br>Каждый выстрел нагревает ядро на 15 градусов. Если перегреть систему, ядро начнет разрушаться. Три аварии — и ядро встанет на 1 час. Следите за датчиками!<br><br><strong>📅 О СЕЗОНАХ:</strong><br>После окончания сезона монеты и звезды сгорают, но алмазы остаются у вас навсегда.`;
    document.getElementById('helpBody').innerHTML = helpContent;
    document.getElementById('helpModal').classList.add('active');
}

function closeHelp() {
    document.getElementById('helpModal').classList.remove('active');
}

function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    const toastIcon = document.getElementById('toastIcon');
    const toastMessage = document.getElementById('toastMessage');
    const icons = { success: '✓', warning: '⚠', error: '✗', info: 'ℹ' };
    toast.className = `toast ${type}`;
    toastIcon.textContent = icons[type];
    toastMessage.textContent = message;
    toast.classList.add('show');
    setTimeout(() => { toast.classList.remove('show'); }, 1000);
}

function showFloatingEarn(row, col, text, type) {
    const fieldGrid = document.getElementById('fieldGrid');
    const padding = 10;
    const cellX = padding + col * (CELL_SIZE + GAP) + CELL_SIZE / 2;
    const cellY = padding + row * (CELL_SIZE + GAP);
    const floatEl = document.createElement('div');
    floatEl.className = 'floating-earn';
    floatEl.textContent = text;
    floatEl.style.left = `${cellX}px`;
    floatEl.style.top = `${cellY}px`;
    if (type === 'coin') {
        floatEl.style.color = '#f1c40f';
        floatEl.style.textShadow = '0 2px 10px rgba(0, 0, 0, 0.8), 0 0 10px rgba(241, 196, 15, 0.5)';
    } else if (type === 'diamond') {
        floatEl.style.color = '#3498db';
        floatEl.style.textShadow = '0 2px 10px rgba(0, 0, 0, 0.8), 0 0 10px rgba(52, 152, 219, 0.5)';
    } else if (type === 'star') {
        floatEl.style.color = '#ff0000';
        floatEl.style.textShadow = '0 2px 10px rgba(0, 0, 0, 0.8), 0 0 10px rgba(255, 0, 0, 0.5)';
    } else if (type === 'multiplier') {
        floatEl.style.color = '#9b59b6';
        floatEl.style.textShadow = '0 2px 10px rgba(0, 0, 0, 0.8), 0 0 10px rgba(155, 89, 182, 0.5)';
        floatEl.style.fontSize = '16px';
        floatEl.style.fontWeight = '800';
    } else if (type === 'router') {
        floatEl.style.color = '#3498db';
        floatEl.style.textShadow = '0 2px 10px rgba(0, 0, 0, 0.8), 0 0 10px rgba(52, 152, 219, 0.5)';
        floatEl.style.fontSize = '14px';
        floatEl.style.fontWeight = '700';
    }
    fieldGrid.appendChild(floatEl);
    setTimeout(() => floatEl.remove(), 1200);
}

// Функция инициализации игры
let gameInitialized = false;
function initGame() {
    if (gameInitialized) return;

    loadGame();
    updateUI();
    startPassiveEffects();

    if (gameState.firstPlay) {
        setTimeout(() => showHelp(), 500);
        gameState.firstPlay = false;
    }

    gameInitialized = true;
}

// loadGame() вызывается из initGame() когда страница готова
// loadGame();

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', () => {
    if (typeof initGame === 'function') {
        initGame();
    }
});
