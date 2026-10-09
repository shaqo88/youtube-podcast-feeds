const CACHE_NAME = "torah-pod-shell-215f8bea1f46";
const SHELL_ASSETS = [
  "./",
  "./index.html",
  "./about/",
  "./explore/",
  "./assets/site.css",
  "./assets/app.js",
  "./assets/storage.js",
  "./assets/accounts-bootstrap.js",
  "./assets/listen-core.js",
  "./assets/theme.js",
  "./assets/fonts/NotoSansHebrew.ttf",
  "./metadata/v1/latest.json",
  "./assets/icon-192.png",
  "./assets/icon-512.png",
  "./manifest.webmanifest",
  "./catalog.json",
  "./catalog-meta.json",
  "./status.json",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET" || request.destination === "audio") return;
  const url = new URL(request.url);
  if (url.pathname.startsWith("/api/") || request.headers.has("Authorization")) return;
  if (url.pathname.includes("/__/auth/") || url.pathname.includes("/auth/callback") || url.searchParams.has("code") || url.searchParams.has("state")) return;
  if (url.pathname.endsWith("/accounts-config.json")) return;
  if (url.origin !== location.origin) return;
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(() => caches.match(request).then((cached) => cached || caches.match("./index.html")))
    );
    return;
  }
  const freshData = url.pathname.endsWith(".json") || url.pathname.endsWith(".xml");
  if (request.destination === "script" || request.destination === "style" || freshData) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(async () => (await caches.match(request)) || ((request.destination === "script" || request.destination === "style") ? caches.match(url.origin + url.pathname) : undefined))
    );
    return;
  }
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request).then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
        }
        return response;
      });
    })
  );
});
