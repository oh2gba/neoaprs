// The Settings tab's Map group in words: sizes, the day the map was downloaded, what the running
// job is doing, and which parts of the daemon's `map` state the button and the map may rely on.
import { monthShort, t } from "@/i18n";
import { bytesText } from "@/lib/format";

import type { MessageId } from "@/i18n/catalogue";
import type { MapSizeEstimate, MapState } from "@/protocol/protocol";

/** The message id for each `step` of the topic `map` in the progress line. */
const STEP_TEXT: Record<MapState["step"], MessageId | ""> = {
  "": "",
  build: "settings.map.step.build",
  world: "settings.map.step.world",
  area: "settings.map.step.area",
};

/**
 * The one plain line about the map on disk ("Map downloaded 23 Oct") when there is a detailed
 * map, else nothing. The world map ships with NeoAPRS and is not mentioned.
 */
export function downloadedLine(map: MapState): string {
  if (!map.detail) return "";
  const day = /^\d{4}-(\d{2})-(\d{2})/.exec(map.detail.modified);
  const month = Number(day?.[1]) - 1;
  return day && month >= 0 && month < 12
    ? t("settings.map.downloaded_on", { day: Number(day[2]), month: monthShort(new Date(2000, month, 15)) })
    : t("settings.map.downloaded");
}

/**
 * The estimate, if it is for the area and zoom the settings ask for now; an older one is not shown.
 */
export function currentEstimate(map: MapState): MapSizeEstimate | null {
  const estimate = map.estimate;
  return estimate !== null && estimate.radius_km === map.radius_km && estimate.maxzoom === map.maxzoom ? estimate : null;
}

export function isRunning(map: MapState): boolean {
  return map.state === "estimating" || map.state === "downloading";
}

/**
 * Why a map job failed or cannot start: the daemon's code (`MapState.problem`, `MapState.blocked`).
 */
const PROBLEMS: Record<NonNullable<MapState["problem"]>["code"], MessageId> = {
  no_position: "settings.map.problem.no_position",
  busy: "settings.map.problem.busy",
  slow: "settings.map.problem.slow",
  unreachable: "settings.map.problem.unreachable",
  no_build: "settings.map.problem.no_build",
  too_big: "settings.map.problem.too_big",
  no_space: "settings.map.problem.no_space",
  failed: "settings.map.problem.failed",
};

/** What the last job failed with; "" if it did not. */
export function problemText(map: MapState): string {
  return map.problem === null ? "" : t(PROBLEMS[map.problem.code] ?? "settings.map.problem.failed", map.problem.params);
}

/** Why no job can start now; "" if one can, or for a code the page has no words for. */
export function blockedText(map: MapState): string {
  const id = map.blocked === "" ? undefined : (PROBLEMS[map.blocked] as MessageId | undefined);
  return id === undefined ? "" : t(id);
}

/**
 * What the job is doing, with percent and size so far and a stall note: `Map of the area 49% ·
 * 340 MB`, `… · no progress: trying again (2 of 3)`.
 */
export function progressText(map: MapState): string {
  const id = STEP_TEXT[map.step];
  const step = id ? t(id) : map.state === "estimating" ? t("settings.map.estimating") : t("settings.map.working");
  return [
    map.percent === null ? step : t("settings.map.step_percent", { step, percent: map.percent }),
    ...(map.downloaded ? [bytesText(map.downloaded)] : []),
    ...(map.retry ? [t("settings.map.retry", { attempt: map.retry.attempt, tries: map.retry.tries })] : []),
  ].join(" · ");
}

/**
 * A change means the daemon's files are other ones (remade, removed or first seen): the map reads
 * them again. Null until known.
 */
export function filesKey(map: MapState | null): string | null {
  return map === null ? null : `${map.detail?.modified ?? "-"} ${map.world?.modified ?? "-"}`;
}

/**
 * The first-run guide's quiet map line, or none: the detailed map is being made automatically
 * (`setup.map_auto`), or could not be fetched yet and will be when online (`setup.map_later`).
 */
export function setupMapLine(map: MapState | null): MessageId | "" {
  if (map === null || map.detail !== null) return "";
  if (map.state === "downloading") return "setup.map_auto";
  return map.later && !isRunning(map) ? "setup.map_later" : "";
}
