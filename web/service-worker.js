const CACHE = "fpfood-v7";
const ASSETS = [
  "index.html",
  "manifest.webmanifest",
  "icons/azienda.png"
];

self.addEventListener("install", (e) => {
  self.skipWaiting(); // attiva subito il nuovo SW
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)));
});

self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)));
    await self.clients.claim(); // prendi subito il controllo delle pagine
  })());
});

self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return;

  const req = e.request;
  const url = req.url;
  const isHTML = req.mode === 'navigate' || (req.headers.get('accept') || '').includes('text/html');

  // 🔒 BYPASS API: mai cache sulle chiamate al backend
  if (url.includes('fpfood-backend.onrender.com')) {
    e.respondWith(fetch(req)); // network-only, nessun caching
    return;
  }

  if (isHTML) {
    // HTML: network-first per evitare index.html stantio
    e.respondWith(
      fetch(req).then(r => {
        const copy = r.clone();
        caches.open(CACHE).then(c => c.put(req, copy));
        return r;
      }).catch(() => caches.match(req))
    );
    return;
  }

  // Asset statici: cache-first con "fill" al primo passaggio
  e.respondWith(
    caches.match(req).then(resp => resp || fetch(req).then(r => {
      const copy = r.clone();
      caches.open(CACHE).then(c => c.put(req, copy));
      return r;
    }).catch(() => new Response("Offline", { status: 503 })))
  );
});