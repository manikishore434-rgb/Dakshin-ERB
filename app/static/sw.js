// Minimal service worker: keeps the order form usable offline (network first, fall back to cache).
const CACHE = 'oto-v1';
const SHELL = ['/m/order', '/static/style.css', '/static/order.js'];
self.addEventListener('install', e => e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())));
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);
  if (!(SHELL.includes(url.pathname) || url.pathname === '/api/catalog')) return;
  e.respondWith(fetch(e.request).then(r => { const copy = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); return r; })
                .catch(() => caches.match(e.request)));
});
