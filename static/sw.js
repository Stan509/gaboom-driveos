/*
 * Gaboom DriveOS — Service Worker
 * Caches static assets, provides offline fallback.
 * Does NOT cache private/dynamic dashboard pages.
 */
const CACHE_NAME = 'gaboom-v1';
const STATIC_ASSETS = [
  '/static/brand/logo.png',
  '/static/brand/icon-192.png',
  '/static/brand/icon-512.png',
  '/static/brand/favicon-32.png',
  '/static/brand/apple-touch-icon.png',
  '/offline/',
];

// Install — pre-cache static assets + offline page
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// Activate — clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch — network-first for navigation, cache-first for static
self.addEventListener('fetch', (event) => {
  const { request } = event;

  // Skip non-GET
  if (request.method !== 'GET') return;

  // Skip API, admin, POST-like endpoints
  const url = new URL(request.url);
  if (url.pathname.startsWith('/admin/') || url.pathname.startsWith('/saas/')) return;

  // Navigation requests — network first, offline fallback
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).catch(() => caches.match('/offline/'))
    );
    return;
  }

  // Static assets — cache first
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request).then((resp) => {
        const clone = resp.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        return resp;
      }))
    );
    return;
  }
});
