// The page's service worker (registered by lib/worker.ts, built into neoaprs/page/sw.js by
// vite.config.ts, which sets `c55529a08e` to a hash of the files). It lets a browser install
// the page as an app and open its shell while the daemon is away; it never stands between the page
// and the daemon:
//  - assets/ (hash-named files): cache first, kept on first use; the ones the shell names are
//    fetched once the shell has come; caches of old builds are deleted when a new worker activates.
//  - the shell (index.html), manifest, icons, symbol sheets and glyph files: network first, the
//    cache only when the daemon cannot be reached (a failed connection or a 5xx), so an update is
//    never hidden behind an old page.
//  - everything else is left to the browser: access routes, base map tiles and byte ranges, any
//    request that is not a GET or has a query, other hosts, sw.js itself. (The socket is not a
//    fetch.)
const BUILD = "c55529a08e";
const PAGE = `neoaprs-${BUILD}-page`;
const ASSETS = `neoaprs-${BUILD}-assets`;
const SHELL = /^(?:|index\.html|manifest\.webmanifest|(?:icons|symbols|fonts)\/.+)$/;
const HASHED = /^assets\/[^/]+-[\w-]{8}\.\w+$/;

/**
 * What the worker does with a request: "assets", "shell", or "" to leave it alone. `scope` is the
 * page folder's address, ending with a slash.
 */
function kind(request, scope) {
  if (request.method !== "GET" || request.headers.has("range") || !request.url.startsWith(scope)) return "";
  const url = new URL(request.url);
  if (url.search !== "") return "";
  const path = decodeURIComponent(url.pathname.slice(new URL(scope).pathname.length));
  if (HASHED.test(path)) return "assets";
  return SHELL.test(path) ? "shell" : "";
}

async function keepAsset(cache, url) {
  try {
    if (await cache.match(url)) return;
    const answer = await fetch(url);
    if (answer.status === 200) await cache.put(url, answer);
  } catch {
    // The page fetches and keeps the file when it asks for it.
  }
}

/** The files of assets/ that the shell names, so the page opens offline after a single visit. */
async function keepAssetsOf(html) {
  const cache = await caches.open(ASSETS);
  const names = new Set(html.match(/\.\/assets\/[^"'()\s]+/g) ?? []);
  await Promise.all(
    [...names]
      .filter((name) => HASHED.test(name.slice(2)))
      .map((name) => keepAsset(cache, new URL(name, self.registration.scope).href)),
  );
}

async function cacheFirst(request) {
  const cache = await caches.open(ASSETS);
  const kept = await cache.match(request);
  if (kept) return kept;
  const answer = await fetch(request);
  if (answer.status === 200) await cache.put(request, answer.clone());
  return answer;
}

/**
 * The network's answer, kept for when it is away. The shell is kept under the folder's own
 * address, whether asked for as it or as index.html.
 */
async function networkFirst(request, event) {
  const cache = await caches.open(PAGE);
  const path = new URL(request.url).pathname;
  const key = path.endsWith("/") || path.endsWith("/index.html") ? self.registration.scope : request;
  try {
    const answer = await fetch(request);
    if (answer.status === 200) {
      await cache.put(key, answer.clone());
      if (key === self.registration.scope) event.waitUntil(answer.clone().text().then(keepAssetsOf));
    }
    return answer.status < 500 ? answer : ((await cache.match(key)) ?? answer);
  } catch (error) {
    const kept = await cache.match(key);
    if (kept) return kept;
    throw error;
  }
}

self.addEventListener("install", () => void self.skipWaiting());

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      for (const name of await caches.keys())
        if (name.startsWith("neoaprs-") && name !== PAGE && name !== ASSETS) await caches.delete(name);
      await self.clients.claim();
      try {
        const answer = await fetch(self.registration.scope);
        if (answer.status === 200) {
          await (await caches.open(PAGE)).put(self.registration.scope, answer.clone());
          await keepAssetsOf(await answer.text());
        }
      } catch {
        // offline: the shell is kept at its next visit
      }
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const which = kind(event.request, self.registration.scope);
  if (which) event.respondWith(which === "assets" ? cacheFirst(event.request) : networkFirst(event.request, event));
});
