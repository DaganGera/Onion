/* SAMA service worker — LOOP-A859 (india-access).
 *
 * Why: a grading officer on rural prepaid data should pay for the static
 * shell (index.html + vendored tailwind.js, ~480 KB) exactly ONCE, not on
 * every visit. Measured numbers live in .agent/IMPACT_EVIDENCE.md §4b.
 *
 * Deliberately boring, by project rule:
 *   - ONLY same-origin GETs are touched, and only two path families:
 *       /static/*        -> stale-while-revalidate (instant cache hit,
 *                           background refresh; server ETags turn the
 *                           refresh into a ~1 KB 304 when online)
 *       /api/replay/N    -> cache-first (payloads are immutable demo
 *                           caches; keeping them makes the ?replay=1
 *                           judge demo survive a radio drop mid-flow)
 *   - Nothing else is intercepted: POST /analyze, /finalize, certificate
 *     pages and every cross-origin request behave exactly as before.
 *   - No build step, no imports, no external fetches in this file.
 *   - Registration is guarded in index.html: on plain-HTTP LAN testing or
 *     engines without serviceWorker support this file simply never loads.
 *
 * Bump CACHE_VERSION whenever shipped assets change semantics; old caches
 * are deleted on activate so stale shells cannot linger.
 */

'use strict';

const CACHE_VERSION = 'sama-a859-v1';

self.addEventListener('install', () => {
  // Take over fast; there is nothing to precache — the runtime cache fills
  // from the traffic the first visit generates anyway.
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(
      names.filter((n) => n !== CACHE_VERSION).map((n) => caches.delete(n))
    );
    await self.clients.claim();
  })());
});

function inScope(url) {
  return url.origin === self.location.origin &&
    (url.pathname.startsWith('/static/') ||
      /^\/api\/replay\/\d+$/.test(url.pathname));
}

async function cacheFirst(request) {
  const hit = await caches.match(request);
  if (hit) return hit;
  try {
    const res = await fetch(request);
    if (res && res.ok) {
      const cache = await caches.open(CACHE_VERSION);
      cache.put(request, res.clone()).catch(() => {});
    }
    return res;
  } catch (err) {
    // Nothing cached and no network: surface the real failure so the
    // page's existing timeout/retry/save-and-retry UI stays truthful.
    throw err;
  }
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE_VERSION);
  const hit = await cache.match(request);
  const refresh = fetch(request).then((res) => {
    if (res && res.ok) {
      cache.put(request, res.clone()).catch(() => {});
    }
    return res;
  }).catch(() => null);
  return hit || (await refresh) || Response.error();
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  let url;
  try { url = new URL(req.url); } catch (e) { return; }
  if (!inScope(url)) return;

  if (url.pathname.startsWith('/api/replay/')) {
    event.respondWith(cacheFirst(req));
  } else {
    event.respondWith(staleWhileRevalidate(req));
  }
});
