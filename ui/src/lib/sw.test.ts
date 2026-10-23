// The service worker (ui/sw/sw.js) run against fakes of what a worker has: its listeners, the Cache API and fetch. What it takes into its caches, what it leaves to the browser, and what it does when the daemon is away.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

const SCOPE = "http://pi.local:7303/app/";
const SOURCE = readFileSync(join(process.cwd(), "sw", "sw.js"), "utf-8");
const ASSET = `${SCOPE}assets/index-AbCd1234.js`;
const HTML = '<script type="module" src="./assets/index-AbCd1234.js"></script><link rel="stylesheet" href="./assets/index-Zy9x8w7v.css">';

type Listener = (event: Record<string, unknown>) => void;
interface Rig {
  fetch: Mock<(request: string | { url: string }) => Promise<Response>>;
  stores: Map<string, Map<string, Response>>;
  claim: ReturnType<typeof vi.fn>;
  skip: ReturnType<typeof vi.fn>;
  /** A fetch event: the answer the worker gave, or undefined when it left the request to the browser; `settle` waits for what it went on to do. */
  ask: (url: string, init?: { method?: string; range?: string; mode?: string }) => Promise<{ answer: Response | undefined; settle: () => Promise<void> }>;
  activate: () => Promise<void>;
  install: () => void;
}

function rig(version = "1.2.3"): Rig {
  const listeners = new Map<string, Listener>();
  const stores = new Map<string, Map<string, Response>>();
  const key = (request: string | { url: string }): string => (typeof request === "string" ? request : request.url);
  const caches = {
    open: (name: string) => {
      const store = stores.get(name) ?? new Map<string, Response>();
      stores.set(name, store);
      return Promise.resolve({
        match: (request: string | { url: string }) => Promise.resolve(store.get(key(request))?.clone()),
        put: (request: string | { url: string }, response: Response) => Promise.resolve(void store.set(key(request), response)),
      });
    },
    keys: () => Promise.resolve([...stores.keys()]),
    delete: (name: string) => Promise.resolve(stores.delete(name)),
  };
  const claim = vi.fn(() => Promise.resolve());
  const skip = vi.fn(() => Promise.resolve());
  const fetcher = vi.fn<(request: string | { url: string }) => Promise<Response>>();
  const self = {
    registration: { scope: SCOPE },
    clients: { claim },
    skipWaiting: skip,
    addEventListener: (type: string, listener: Listener) => listeners.set(type, listener),
  };
  // eslint-disable-next-line @typescript-eslint/no-implied-eval, @typescript-eslint/no-unsafe-call -- the worker is a script that is run here with the globals of a worker, which are fakes
  new Function("self", "caches", "fetch", SOURCE.replaceAll("__PAGE_VERSION__", version))(self, caches, fetcher);
  return {
    fetch: fetcher,
    stores,
    claim,
    skip,
    install: () => listeners.get("install")?.({}),
    activate: async () => {
      let done: Promise<void> | undefined;
      listeners.get("activate")?.({ waitUntil: (promise: Promise<void>) => (done = promise) });
      await done;
    },
    ask: async (url, init = {}) => {
      let answer: Promise<Response> | undefined;
      const pending: Promise<unknown>[] = [];
      const request = { url, method: init.method ?? "GET", mode: init.mode ?? "cors", headers: new Headers(init.range ? { range: init.range } : {}) };
      listeners.get("fetch")?.({
        request,
        respondWith: (promise: Promise<Response>) => (answer = promise),
        waitUntil: (promise: Promise<unknown>) => pending.push(promise),
      });
      const settle = async (): Promise<void> => void (await Promise.all(pending));
      return { answer: await answer, settle };
    },
  };
}

const reply = (body: string, status = 200): Response => new Response(body, { status });

describe("what the worker leaves to the browser", () => {
  let r: Rig;
  beforeEach(() => {
    r = rig();
    r.fetch.mockImplementation(() => Promise.resolve(reply("x")));
  });

  it.each([
    ["the access routes", `${SCOPE}access`, {}],
    ["a new key", `${SCOPE}access/new`, {}],
    ["the base map", `${SCOPE}basemap.pmtiles`, {}],
    ["a piece of the base map", `${SCOPE}basemap.pmtiles`, { range: "bytes=0-99" }],
    ["the world map", `${SCOPE}basemap-world.pmtiles`, {}],
    ["a file of assets/ asked for in pieces", ASSET, { range: "bytes=0-9" }],
    ["a request that is not a GET", `${SCOPE}index.html`, { method: "POST" }],
    ["a file with a query", `${SCOPE}index.html?x=1`, {}],
    ["another site", "https://tiles.example/a.js", {}],
    ["another folder of the same host", "http://pi.local:7303/other/assets/index-AbCd1234.js", {}],
    ["the worker itself", `${SCOPE}sw.js`, {}],
    ["a path the page does not have", `${SCOPE}nothing.json`, {}],
    ["a name that only looks like a hashed file", `${SCOPE}assets/sub/index-AbCd1234.js/../x`, {}],
  ])("%s", async (_what, url, init) => {
    expect((await r.ask(url, init)).answer).toBeUndefined();
    expect(r.fetch).not.toHaveBeenCalled();
    expect(r.stores.size).toBe(0);
  });

  it("answers the files of the page and of assets/ (the shell, the manifest, icons, symbols, fonts, the hashed files)", async () => {
    for (const path of [
      "",
      "index.html",
      "manifest.webmanifest",
      "icons/icon-192.png",
      "symbols/primary.png",
      "fonts/NotoSans-Regular/0-255.pbf",
      "assets/maplibre-gl-worker-Qw3rTy-_.mjs",
    ]) {
      expect((await r.ask(SCOPE + path)).answer, path).toBeInstanceOf(Response);
    }
  });
});

describe("the hashed files of assets/: cache first", () => {
  it("takes a file from the network once and from the cache after that", async () => {
    const r = rig();
    r.fetch.mockImplementation(() => Promise.resolve(reply("code")));
    expect(await (await r.ask(ASSET)).answer?.text()).toBe("code");
    expect(r.fetch).toHaveBeenCalledTimes(1);
    r.fetch.mockImplementation(() => Promise.reject(new Error("offline")));
    expect(await (await r.ask(ASSET)).answer?.text()).toBe("code");
    expect(r.fetch).toHaveBeenCalledTimes(1);
  });

  it("keeps nothing that was not a plain 200", async () => {
    const r = rig();
    r.fetch.mockImplementation(() => Promise.resolve(reply("no", 404)));
    expect((await r.ask(ASSET)).answer?.status).toBe(404);
    expect(r.stores.get("neoaprs-1.2.3-assets")?.size).toBe(0);
  });
});

describe("the shell and the other files of the page: network first", () => {
  it("shows what the network says, and keeps it for the day the daemon is away", async () => {
    const r = rig();
    r.fetch.mockImplementation(() => Promise.resolve(reply("new page")));
    const first = await r.ask(`${SCOPE}index.html`);
    expect(await first.answer?.text()).toBe("new page");
    r.fetch.mockImplementation(() => Promise.resolve(reply("newer page")));
    expect(await (await r.ask(SCOPE)).answer?.text()).toBe("newer page");
    r.fetch.mockImplementation(() => Promise.reject(new TypeError("Failed to fetch")));
    expect(await (await r.ask(`${SCOPE}index.html`, { mode: "navigate" })).answer?.text()).toBe("newer page");
    expect(await (await r.ask(SCOPE, { mode: "navigate" })).answer?.text()).toBe("newer page");
  });

  it("falls back to the cache for a 5xx from something in front of the daemon, and shows the 5xx when there is nothing kept", async () => {
    const r = rig();
    r.fetch.mockImplementation(() => Promise.resolve(reply("bad gateway", 502)));
    expect((await r.ask(SCOPE)).answer?.status).toBe(502);
    r.fetch.mockImplementation(() => Promise.resolve(reply("page")));
    await r.ask(SCOPE);
    r.fetch.mockImplementation(() => Promise.resolve(reply("bad gateway", 502)));
    expect(await (await r.ask(SCOPE)).answer?.text()).toBe("page");
  });

  it("does not hide a 403 or a 404 behind the cache, and has nothing to say for a daemon that is away at the first visit", async () => {
    const r = rig();
    r.fetch.mockImplementation(() => Promise.resolve(reply("page")));
    await r.ask(SCOPE);
    r.fetch.mockImplementation(() => Promise.resolve(reply("not ours", 403)));
    expect((await r.ask(SCOPE)).answer?.status).toBe(403);
    r.fetch.mockImplementation(() => Promise.reject(new TypeError("Failed to fetch")));
    await expect(r.ask(`${SCOPE}manifest.webmanifest`)).rejects.toThrow("Failed to fetch");
  });

  it("keeps the files of assets/ the shell names, so that the page opens offline after one visit", async () => {
    const r = rig();
    r.fetch.mockImplementation((request) => {
      const url = typeof request === "string" ? request : request.url;
      return Promise.resolve(reply(url.endsWith("/app/") ? HTML : `file ${url}`));
    });
    await (await r.ask(SCOPE)).settle();
    const assets = r.stores.get("neoaprs-1.2.3-assets");
    expect([...(assets?.keys() ?? [])].sort()).toEqual([`${SCOPE}assets/index-AbCd1234.js`, `${SCOPE}assets/index-Zy9x8w7v.css`]);
  });
});

describe("a new version", () => {
  it("takes over at once", () => {
    const r = rig();
    r.install();
    expect(r.skip).toHaveBeenCalled();
  });

  it("deletes the caches of the old versions, and only NeoAPRS's own, and fills its own", async () => {
    const r = rig("2.0.0");
    r.fetch.mockImplementation(() => Promise.resolve(reply(HTML)));
    for (const name of ["neoaprs-1.9.0-page", "neoaprs-1.9.0-assets", "neoaprs-2.0.0-page", "someone-elses"]) r.stores.set(name, new Map());
    await r.activate();
    expect([...r.stores.keys()].sort()).toEqual(["neoaprs-2.0.0-assets", "neoaprs-2.0.0-page", "someone-elses"]);
    expect(r.claim).toHaveBeenCalled();
    expect(r.stores.get("neoaprs-2.0.0-page")?.has(SCOPE)).toBe(true);
    expect(r.stores.get("neoaprs-2.0.0-assets")?.size).toBe(2);
  });

  it("activates with the daemon away", async () => {
    const r = rig();
    r.fetch.mockImplementation(() => Promise.reject(new TypeError("Failed to fetch")));
    await expect(r.activate()).resolves.toBeUndefined();
    expect(r.claim).toHaveBeenCalled();
  });
});
