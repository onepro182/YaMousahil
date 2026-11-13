self.addEventListener('install', function () {
  self.skipWaiting();
});

self.addEventListener('activate', function (event) {
  event.waitUntil(self.clients.claim());
});

// Minimal fetch handler: pass-through (keeps SW active and allows notifications)
self.addEventListener('fetch', function () {});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  event.waitUntil((async function () {
    const all = await clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const c of all) {
      if ('focus' in c) { try { await c.focus(); return; } catch (e) {} }
    }
    if (clients.openWindow) {
      try { await clients.openWindow('./'); } catch (e) {}
    }
  })());
});
