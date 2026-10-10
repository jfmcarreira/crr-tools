self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(clients.claim());
});

self.addEventListener('push', (event) => {
    let data = {};
    try { data = event.data ? event.data.json() : {}; } catch (_) { /* Default message. */ }
    event.waitUntil(self.registration.showNotification(data.title || 'Contínuos CRR', {
        body: data.body || 'Tens uma atualização nos teus turnos.',
        data: {url: data.url || self.registration.scope}
    }));
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const url = new URL(event.notification.data.url, self.registration.scope);
    const target = url.href.startsWith(self.registration.scope) ? url.href : self.registration.scope;
    event.waitUntil(clients.matchAll({type: 'window', includeUncontrolled: true}).then(async (windows) => {
        for (const client of windows) {
            if (client.url === target && 'focus' in client) return client.focus();
        }
        return clients.openWindow(target);
    }));
});

self.addEventListener('fetch', (event) => {
    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request).catch(() => caches.match('/'))
        );
    }
});
