// RedPulse Bot Service Worker
// Управляет кэшированием и обновлениями

const CACHE_NAME = 'redpulse-v0.1.5';
const ASSETS_TO_CACHE = [
    '/',
    '/webapp',
    '/webapp/index.html',
    '/webapp/pf_styles.css'
];

// Установка Service Worker
self.addEventListener('install', (event) => {
    console.log('[SW] Установка, версия:', CACHE_NAME);
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            console.log('[SW] Кэширование ресурсов');
            return cache.addAll(ASSETS_TO_CACHE);
        })
    );
    // Активируем сразу
    self.skipWaiting();
});

// Активация и очистка старого кэша
self.addEventListener('activate', (event) => {
    console.log('[SW] Активация, версия:', CACHE_NAME);
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('[SW] Удаление старого кэша:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
    // Берём контроль над страницами сразу
    self.clients.claim();
});

// Обработка запросов - всегда загружаем из сети, кэш как запасной вариант
self.addEventListener('fetch', (event) => {
    // API запросы всегда идут в сеть
    if (event.request.url.includes('/api/')) {
        event.respondWith(
            fetch(event.request).catch(() => {
                return new Response(JSON.stringify({ error: 'OFFLINE' }), {
                    status: 503,
                    headers: { 'Content-Type': 'application/json' }
                });
            })
        );
        return;
    }

    // Для HTML всегда сеть с проверкой кэша
    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request).catch(() => {
                return caches.match(event.request);
            })
        );
        return;
    }

    // Остальные ресурсы - сеть с кэшем как запасным вариантом
    event.respondWith(
        fetch(event.request)
            .then((response) => {
                // Кэшируем успешные ответы
                if (response.ok) {
                    const responseClone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, responseClone);
                    });
                }
                return response;
            })
            .catch(() => {
                return caches.match(event.request);
            })
    );
});

// Сообщение от клиента для проверки версии
self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'CHECK_VERSION') {
        event.ports[0].postMessage({ version: CACHE_NAME });
    }
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});
