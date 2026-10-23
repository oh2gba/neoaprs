// The Map group of the Settings tab, in words: sizes, the day the map was downloaded, what the running job is doing, and which of the daemon's `map` state the button and the map may rely on.
import type { MapSizeEstimate, MapState } from "@/protocol/protocol";

/** What `step` of the topic `map` is called in the progress line. */
const STEP_TEXT: Record<MapState["step"], string> = {
  "": "",
  tool: "Fetching the pmtiles program",
  build: "Finding the latest build",
  world: "World map",
  area: "Map of the area",
};

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

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** The one plain line about the map on disk: "Map downloaded 23 Oct" when there is a detailed map, else nothing. The world map ships with NeoAPRS and is not mentioned; the rest is in the log. */
export function downloadedLine(map: MapState): string {
  if (!map.detail) return "";
  const day = /^\d{4}-(\d{2})-(\d{2})/.exec(map.detail.modified);
  const month = MONTHS[Number(day?.[1]) - 1];
  return day && month ? `Map downloaded ${Number(day[2])} ${month}` : "Map downloaded";
}

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
