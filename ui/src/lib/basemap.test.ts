import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BASEMAP_FILE, WORLD_FILE } from "@/lib/basemapstyle";
import type { archivesPresent as ArchivesPresent, loadMapEngine as LoadMapEngine } from "@/lib/basemap";

// MapLibre and the PMTiles reader are the library's own and heavy; what is tested is what the page asks of them: the worker file, the protocol, once, and a load that fails is tried again.
const library = vi.hoisted(() => ({
  setWorkerUrl: vi.fn(),
  addProtocol: vi.fn(),
  tile: vi.fn(),
  offline: false,
  protocols: 0,
}));

vi.mock("maplibre-gl", () => ({ setWorkerUrl: library.setWorkerUrl, addProtocol: library.addProtocol }));
vi.mock("pmtiles", () => ({
  Protocol: class {
    tile = library.tile;
    constructor() {
      if (library.offline) throw new Error("the page is offline");
      library.protocols += 1;
    }
  },
}));
vi.mock("maplibre-gl/dist/maplibre-gl-worker.mjs?url", () => ({ default: "assets/maplibre-gl-worker-abc123.js" }));
vi.mock("maplibre-gl/dist/maplibre-gl.css", () => ({}));

async function basemap(): Promise<{
  loadMapEngine: typeof LoadMapEngine;
  archivesPresent: typeof ArchivesPresent;
  archiveUrl: (file?: string, version?: string) => string;
  glyphsUrl: () => string;
}> {
  vi.resetModules();
  return import("@/lib/basemap");
}

beforeEach(() => {
  library.setWorkerUrl.mockClear();
  library.addProtocol.mockClear();
  library.protocols = 0;
  library.offline = false;
});
afterEach(() => vi.unstubAllGlobals());

describe("loadMapEngine", () => {
  it("sets up the worker file of the page, as an absolute address, and the pmtiles protocol, and gives the library", async () => {
    const { loadMapEngine } = await basemap();
    const engine = await loadMapEngine();
    expect(engine.setWorkerUrl).toBe(library.setWorkerUrl);
    expect(library.setWorkerUrl).toHaveBeenCalledWith("http://127.0.0.1:7303/assets/maplibre-gl-worker-abc123.js");
    expect(library.addProtocol).toHaveBeenCalledWith("pmtiles", library.tile);
  });

  it("sets up once, however many maps ask", async () => {
    const { loadMapEngine } = await basemap();
    const [first, second] = await Promise.all([loadMapEngine(), loadMapEngine()]);
    await loadMapEngine();
    expect(first).toBe(second);
    expect(library.setWorkerUrl).toHaveBeenCalledTimes(1);
    expect(library.addProtocol).toHaveBeenCalledTimes(1);
    expect(library.protocols).toBe(1);
  });

  it("is tried again by the next map when it failed (the page was offline for a moment)", async () => {
    const { loadMapEngine } = await basemap();
    library.offline = true;
    await expect(loadMapEngine()).rejects.toThrow();
    expect(library.addProtocol).not.toHaveBeenCalled();
    library.offline = false;
    const again = await loadMapEngine();
    expect(again.addProtocol).toBe(library.addProtocol);
  });
});

describe("the addresses of the files the daemon serves", () => {
  it("is the archive as an absolute address on the page's own host, with the version of the file as a query when there is one", async () => {
    const { archiveUrl } = await basemap();
    expect(archiveUrl()).toBe(`http://127.0.0.1:7303/${BASEMAP_FILE}`);
    expect(archiveUrl(WORLD_FILE)).toBe(`http://127.0.0.1:7303/${WORLD_FILE}`);
    expect(archiveUrl(BASEMAP_FILE, "3")).toBe(`http://127.0.0.1:7303/${BASEMAP_FILE}?v=3`);
    expect(archiveUrl(BASEMAP_FILE, "")).not.toContain("?");
  });

  it("has the glyph files of the page as the template MapLibre fills in, absolute", async () => {
    const { glyphsUrl } = await basemap();
    expect(glyphsUrl()).toBe("http://127.0.0.1:7303/fonts/{fontstack}/{range}.pbf");
  });
});

describe("archivesPresent", () => {
  function daemonWith(files: Record<string, number | "down">): string[] {
    const asked: string[] = [];
    vi.stubGlobal("fetch", (input: string, init?: RequestInit) => {
      asked.push(`${init?.method ?? "GET"} ${new URL(input).pathname}`);
      const answer = files[new URL(input).pathname.slice(1)] ?? 404;
      return answer === "down" ? Promise.reject(new TypeError("network")) : Promise.resolve(new Response(null, { status: answer }));
    });
    return asked;
  }

  it("asks for each file with a HEAD request, which does not read it", async () => {
    const { archivesPresent } = await basemap();
    const asked = daemonWith({ [BASEMAP_FILE]: 200, [WORLD_FILE]: 200 });
    expect(await archivesPresent()).toEqual({ detail: true, world: true });
    expect(asked.sort()).toEqual([`HEAD /${BASEMAP_FILE}`, `HEAD /${WORLD_FILE}`].sort());
  });

  it("says which of the two is there", async () => {
    const { archivesPresent } = await basemap();
    daemonWith({ [WORLD_FILE]: 200 });
    expect(await archivesPresent()).toEqual({ detail: false, world: true });
  });

  it("takes anything but a 200 for a file that is not there, and a daemon that does not answer for no base map", async () => {
    const { archivesPresent } = await basemap();
    daemonWith({ [BASEMAP_FILE]: 206, [WORLD_FILE]: "down" });
    expect(await archivesPresent()).toEqual({ detail: false, world: false });
  });
});
