// Sport Board Service Worker
// Seite: zuerst aus dem Netz (frische Daten), nach 4 Sekunden oder offline aus dem Zwischenspeicher.
// Schriften und Icons: aus dem Zwischenspeicher, die ändern sich nicht.
const CACHE = "sportboard-v2";
const SHELL = ["./", "manifest.webmanifest", "apple-touch-icon.png", "icon-192.png", "icon-512.png", "fonts/archivo.woff2", "fonts/big-shoulders.woff2"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});

function pageKey(url) {
  // index.html, ./ und Abrufe mit ?fresh=… landen unter demselben Eintrag
  const u = new URL(url);
  const p = u.pathname.endsWith("/index.html") ? u.pathname.slice(0, -10) : u.pathname;
  return u.origin + p;
}

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  const isPage = req.mode === "navigate" || req.destination === "document" || url.pathname.endsWith("/") || url.pathname.endsWith(".html");
  if (isPage) {
    const key = pageKey(req.url);
    e.respondWith(new Promise(resolve => {
      let done = false;
      const fromCache = () => caches.match(key).then(m => m || caches.match("./"));
      const timer = setTimeout(() => { fromCache().then(m => { if (m && !done) { done = true; resolve(m); } }); }, 4000);
      fetch(req, { cache: "no-store" }).then(r => {
        if (r.ok) { const copy = r.clone(); caches.open(CACHE).then(c => c.put(key, copy)); }
        clearTimeout(timer);
        if (!done) { done = true; resolve(r); }
      }).catch(() => {
        clearTimeout(timer);
        fromCache().then(m => { if (!done) { done = true; resolve(m || Response.error()); } });
      });
    }));
    return;
  }

  e.respondWith(caches.match(req).then(m => m || fetch(req).then(r => {
    if (r.ok) { const copy = r.clone(); caches.open(CACHE).then(c => c.put(req, copy)); }
    return r;
  })));
});
