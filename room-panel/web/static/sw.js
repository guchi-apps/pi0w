const CACHE_NAME = "room-panel-shell-v1";
const APP_SHELL = [
  "/static/base.css",
  "/static/lcd.css",
  "/static/led.css",
  "/static/app.js",
  "/static/manifest.json",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) => Promise.all(names.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET" || new URL(req.url).origin !== self.location.origin) {
    return;
  }

  if (new URL(req.url).pathname.startsWith("/static/")) {
    // 静的アセットはキャッシュ優先(ファイル内容は変わらない前提)
    event.respondWith(caches.match(req).then((cached) => cached || fetch(req)));
    return;
  }

  // ページ・APIはLAN内の実機状態を優先するためネットワーク優先。
  // オフライン時のみ直前にキャッシュした内容を表示する。
  event.respondWith(
    fetch(req)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
        return res;
      })
      .catch(() => caches.match(req))
  );
});

