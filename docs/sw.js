// Wishly 2.5: NO application/auth data caching; offline informational screen only.
const VERSION = 'wishly-offline-2.5.0';
self.addEventListener('install', event => {
  event.waitUntil(caches.open(VERSION).then(cache => cache.add('./offline.html')).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(Promise.all([caches.keys().then(keys => Promise.all(keys.filter(key => key !== VERSION).map(key => caches.delete(key)))),self.clients.claim()]));
});
self.addEventListener('fetch', event => {
  const req=event.request;
  if(req.mode !== 'navigate' || req.method !== 'GET') return;
  // Never store full application HTML, credentials, gifts, or shared links.
  event.respondWith(fetch(req).catch(() => caches.match('./offline.html')));
});
