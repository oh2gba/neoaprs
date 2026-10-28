// The Map group of the Settings tab, in words: sizes, the day the map was downloaded, what the running job is doing, and which of the daemon's `map` state the button and the map may rely on.
import { formatNumber, locale, t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import { PSEUDO, SOURCE } from "@/i18n/locales";
import type { MapSizeEstimate, MapState } from "@/protocol/protocol";

/** What `step` of the topic `map` is called in the progress line (the id of the words). */
const STEP_TEXT: Record<MapState["step"], MessageId | ""> = {
  "": "",
  tool: "settings.map.step.tool",
  build: "settings.map.step.build",
  world: "settings.map.step.world",
  area: "settings.map.step.area",
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
  return `${formatNumber(value, digits)} ${units[unit]}`;
}

/** The short name of a month (0 is January) in the language of the page: "Oct". */
function monthShort(month: number): string {
  return new Intl.DateTimeFormat(locale.value === PSEUDO ? SOURCE : locale.value, { month: "short", timeZone: "UTC" }).format(
    new Date(Date.UTC(2000, month, 15)),
  );
}

/** The one plain line about the map on disk: "Map downloaded 23 Oct" when there is a detailed map, else nothing. The world map ships with NeoAPRS and is not mentioned; the rest is in the log. */
export function downloadedLine(map: MapState): string {
  if (!map.detail) return "";
  const day = /^\d{4}-(\d{2})-(\d{2})/.exec(map.detail.modified);
  const month = Number(day?.[1]) - 1;
  return day && month >= 0 && month < 12 ? t("settings.map.downloaded_on", { day: Number(day[2]), month: monthShort(month) }) : t("settings.map.downloaded");
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
  const id = STEP_TEXT[map.step];
  const step = id ? t(id) : map.state === "estimating" ? t("settings.map.estimating") : t("settings.map.working");
  return [
    map.percent === null ? step : t("settings.map.step_percent", { step, percent: map.percent }),
    ...(map.downloaded ? [formatBytes(map.downloaded)] : []),
    ...(map.note ? [map.note] : []),
  ].join(" · ");
}

/** A change in this means the files on the daemon are other ones (made again, removed, or the first time): the map reads them again. Null until the daemon has told. */
export function filesKey(map: MapState | null): string | null {
  return map === null ? null : `${map.detail?.modified ?? "-"} ${map.world?.modified ?? "-"}`;
}

/** The one quiet line of the first-run guide about the map, or none: the detailed map is being made without a click (`setup.map_auto`), or it could not be fetched yet and will be when the computer is online (`setup.map_later`). */
export function setupMapLine(map: MapState | null): MessageId | "" {
  if (map === null || map.detail !== null) return "";
  if (map.state === "downloading") return "setup.map_auto";
  return map.later && !isRunning(map) ? "setup.map_later" : "";
}
