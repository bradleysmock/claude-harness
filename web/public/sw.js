const CACHE_NAME = 'flock-v1';
const PRECACHE_URLS = ['/', '/index.html'];

// ── Install ────────────────────────────────────────────────────────────────────

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS)),
  );
});

// ── Activate ───────────────────────────────────────────────────────────────────

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))),
    ),
  );
});

// ── Fetch ──────────────────────────────────────────────────────────────────────

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirstWithTimeout(event.request));
  } else {
    event.respondWith(cacheFirst(event.request));
  }
});

// Network-first with 2s timeout; fall back to cache; synthetic 503 on total miss.
async function networkFirstWithTimeout(request) {
  const timeout = new Promise((resolve) => setTimeout(() => resolve(null), 2000));

  let networkResponse = null;
  try {
    networkResponse = await Promise.race([fetch(request.clone()), timeout]);
  } catch {
    networkResponse = null;
  }

  if (networkResponse && networkResponse.ok) {
    const clone = networkResponse.clone();
    caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
    return networkResponse;
  }

  const cached = await caches.match(request);
  if (cached) return cached;

  return new Response(JSON.stringify({ error: 'offline-no-cache' }), {
    status: 503,
    headers: { 'Content-Type': 'application/json' },
  });
}

// Cache-first; fall back to network.
async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  return fetch(request);
}
