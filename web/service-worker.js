const CACHE = "fpfood-v2";
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
  const isHTML = req.mode === 'navigate' || (req.headers.get('accept') || '').includes('text/html');

  if (isHTML) {
    // HTML: network-first così non rimani con index.html vecchio
    e.respondWith(
      fetch(req).then(r => {
        const copy = r.clone();
        caches.open(CACHE).then(c => c.put(req, copy));
        return r;
      }).catch(() => caches.match(req))
    );
    return;
  }

  // Asset statici: cache-first con salvataggio in cache al primo passaggio
  e.respondWith(
    caches.match(req).then(resp => resp || fetch(req).then(r => {
      const copy = r.clone();
      caches.open(CACHE).then(c => c.put(req, copy));
      return r;
    }).catch(() => new Response("Offline", { status: 503 })))
  );
});