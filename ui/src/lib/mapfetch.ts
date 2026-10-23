// The Map group of the Settings tab, in words: sizes, areas and dates of the map files, what the running job is doing, and which of the daemon's `map` state the buttons and the map may rely on.
import type { MapFileInfo, MapSizeEstimate, MapState } from "@/protocol/protocol";

/** What `step` of the topic `map` is called in the progress line. */
const STEP_TEXT: Record<MapState["step"], string> = {
  "": "",
  tool: "Fetching the pmtiles program",
  build: "Finding the latest build",
  world: "World map",
  area: "Map of the area",
};

/** The detail choices of the settings form: the deepest zoom, with a word for what it shows. */
export const DETAIL_CHOICES = [
  { value: "10", label: "10 town" },
  { value: "12", label: "12 streets" },
  { value: "14", label: "14 houses" },
] as const;

/** Bytes as the pmtiles program writes them (thousands): `15 kB`, `493 MB`, `1.2 GB`. */
export function formatBytes(bytes: number): string {
  const units = ["B", "kB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1000 && unit < units.length - 1) {
    value /= 1000;
    unit += 1;
  }
  const digits = unit === 0 || value >= 10 ? 0 : 1;
  return `${value.toFixed(digits)} ${units[unit]}`;
}

function degrees(value: number, positive: string, negative: string): string {
  return `${Math.abs(value).toFixed(1)}${value < 0 ? negative : positive}`;
}

/** An area given as [west, south, east, north]: `58.8N to 61.5N, 22.1E to 27.8E`. */
export function formatBox(box: readonly number[]): string {
  const [west, south, east, north] = box;
  if (west === undefined || south === undefined || east === undefined || north === undefined) return "";
  return `${degrees(south, "N", "S")} to ${degrees(north, "N", "S")}, ${degrees(west, "E", "W")} to ${degrees(east, "E", "W")}`;
}

/** The day of a time stamp (`2026-10-22T19:03:53Z`). */
export function formatDay(iso: string): string {
  return iso.slice(0, 10);
}

/** One map file in a line: its area (not the world's), its deepest zoom, its size and the day it was made. */
export function describeFile(file: MapFileInfo, withArea: boolean): string {
  const parts = [
    ...(withArea && file.bbox ? [formatBox(file.bbox)] : []),
    ...(file.max_zoom === null ? [] : [`zoom ${file.max_zoom}`]),
    formatBytes(file.bytes),
    formatDay(file.modified),
  ];
  return parts.join(", ");
}

/** The lines about the files on disk, each saying what it is: the detailed map first, then the world's. */
export function fileLines(map: MapState): string[] {
  return [
    ...(map.detail ? [`Detailed map here: ${describeFile(map.detail, true)}`] : []),
    ...(map.world ? [`World map here: ${describeFile(map.world, false)}`] : []),
  ];
}

/** A download over this many bytes is asked about first (Download 513 MB?): a mobile connection or a small card would feel it. */
export const BIG_DOWNLOAD_BYTES = 200_000_000;

/** The estimate, if it is for the area and the zoom the settings ask for now; an older one is not shown. */
export function currentEstimate(map: MapState): MapSizeEstimate | null {
  const estimate = map.estimate;
  return estimate !== null && estimate.radius_km === map.radius_km && estimate.maxzoom === map.maxzoom ? estimate : null;
}

export function isRunning(map: MapState): boolean {
  return map.state === "estimating" || map.state === "downloading";
}

/** What the job is doing, with its percent and the size so far when it has them, and a note about a stall: `Map of the area 49% · 340 MB`. */
export function progressText(map: MapState): string {
  const step = STEP_TEXT[map.step] || (map.state === "estimating" ? "Estimating" : "Working");
  return [
    map.percent === null ? step : `${step} ${map.percent}%`,
    ...(map.downloaded ? [formatBytes(map.downloaded)] : []),
    ...(map.note ? [map.note] : []),
  ].join(" · ");
}

/** A change in this means the files on the daemon are other ones (made again, removed, or the first time): the map reads them again. Null until the daemon has told. */
export function filesKey(map: MapState | null): string | null {
  return map === null ? null : `${map.detail?.modified ?? "-"} ${map.world?.modified ?? "-"}`;
}
