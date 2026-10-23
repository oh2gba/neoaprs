// MapLibre and the PMTiles reader, loaded when the map is first drawn and set up once: the protocol `pmtiles://` for the archive the daemon serves, and the worker file the page ships. The
// Content-Security-Policy (web/headers.py) has no blob: for workers, and MapLibre makes its worker from a blob unless it is given a file.
import type * as MapLibre from "maplibre-gl";
import { BASEMAP_FILE, WORLD_FILE } from "@/lib/basemapstyle";

type MapEngine = typeof MapLibre;

let engine: Promise<MapEngine> | null = null;

export function loadMapEngine(): Promise<MapEngine> {
  engine ??= setUp().catch((e: unknown) => {
    engine = null; // a failed load (the page is offline for a moment) is tried again by the next map
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

/** The URL of a file the daemon serves, absolute: the style names it after `pmtiles://`, where a relative one would not be resolved against the page. `version` (the file's date) is a query that changes when the
 * file is made again, so that the reader of the archive does not go on with the directories it kept of the old one. */
export function archiveUrl(file: string = BASEMAP_FILE, version = ""): string {
  const url = new URL(file, document.baseURI);
  if (version) url.searchParams.set("v", version);
  return url.href;
}

/** The glyph files of the page (public/fonts), as the template MapLibre fills in. Absolute: the worker that asks for them is a file of assets/ and would resolve a relative one there. */
export function glyphsUrl(): string {
  return `${new URL("fonts/", document.baseURI).href}{fontstack}/{range}.pbf`;
}

/** Whether the daemon has a file (a HEAD request: the file is not read). Absent, or the daemon not answering, is no base map. */
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
