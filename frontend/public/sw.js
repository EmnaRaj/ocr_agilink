// Minimal service worker — just enough to make the app installable and to keep
// working (shell) if the network drops. Deliberately NOT an aggressive cache:
// navigations are network-first (always get the latest UI), API calls are never
// cached (data must be live), hashed assets are cached by the browser normally.
const SHELL = "agilink-shell-v1";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.pathname.startsWith("/api/")) return; // live data, no cache
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req)
        .then((res) => {
          caches.open(SHELL).then((c) => c.put("/index.html", res.clone()));
          return res;
        })
        .catch(() => caches.match("/index.html"))
    );
  }
});
