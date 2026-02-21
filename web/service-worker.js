const CACHE = "fpfood-v1";
const ASSETS = [
  "index.html",
  "manifest.webmanifest",
  "icons/azienda.png"
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
});

self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return;

  e.respondWith(
    caches.match(e.request).then((resp) =>
      resp || fetch(e.request).catch(() =>
        new Response("Offline", { status: 503 })
      )
    )
  );
});