// Kill switch. The web app used to be served from the site root with a service worker here;
// it now lives at ./app/. This worker replaces the old one, clears its caches and unregisters.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil((async () => {
  const keys = await caches.keys();
  await Promise.all(keys.filter((k) => !k.includes('/app/')).map((k) => caches.delete(k)));
  await self.registration.unregister();
  const clients = await self.clients.matchAll({ type: 'window' });
  clients.forEach((c) => c.navigate(c.url));
})()));
