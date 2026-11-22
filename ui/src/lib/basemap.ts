// MapLibre and the PMTiles reader, loaded when the map is first drawn and set up once: the
// `pmtiles://` protocol for the archive the daemon serves, and the page's own worker file. The CSP
// (web/headers.py) has no blob: for workers, and MapLibre makes its worker from a blob unless it
// is given a file.
import type * as MapLibre from "maplibre-gl";
import { BASEMAP_FILE, WORLD_FILE } from "@/lib/basemapstyle";

type MapEngine = typeof MapLibre;

let engine: Promise<MapEngine> | null = null;

export function loadMapEngine(): Promise<MapEngine> {
  engine ??= setUp().catch((e: unknown) => {
    // A failed load (a brief offline spell) is retried by the next map.
    engine = null;
    throw e;
  });
  return engine;
}

async function setUp(): Promise<MapEngine> {
  const [maplibre, pmtiles, worker] = await Promise.all([
    import("maplibre-gl"),
    import("pmtiles"),
    import("maplibre-gl/dist/maplibre-gl-worker.mjs?url"),
    import("maplibre-gl/dist/maplibre-gl.css"),
  ]);
  maplibre.setWorkerUrl(new URL(worker.default, document.baseURI).href);
  maplibre.addProtocol("pmtiles", new pmtiles.Protocol().tile);
  return maplibre;
}

/**
 * The absolute URL of a file the daemon serves (the style names it after `pmtiles://`, where a
 * relative one would not resolve). `version` is a query that changes when the file is remade, so
 * the archive reader drops the directories it cached.
 */
export function archiveUrl(file: string = BASEMAP_FILE, version = ""): string {
  const url = new URL(file, document.baseURI);
  if (version) url.searchParams.set("v", version);
  return url.href;
}

/**
 * The glyph template MapLibre fills in. Absolute, as the asset worker would resolve a relative one
 * wrongly.
 */
export function glyphsUrl(): string {
  return `${new URL("fonts/", document.baseURI).href}{fontstack}/{range}.pbf`;
}

/** Whether the daemon has a file (HEAD request). Absent or no answer means no base map. */
async function present(file: string): Promise<boolean> {
  try {
    return (await fetch(archiveUrl(file), { method: "HEAD" })).status === 200;
  } catch {
    return false;
  }
}

/** Which of the two archives the daemon has. */
export async function archivesPresent(): Promise<{ detail: boolean; world: boolean }> {
  const [detail, world] = await Promise.all([present(BASEMAP_FILE), present(WORLD_FILE)]);
  return { detail, world };
}
