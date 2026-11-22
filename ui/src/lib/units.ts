// Every measured value the page shows, in metric units or in the station's non-metric ones
// (the setting `units/non_metric`, kept by the daemon). What goes on the air and what the operator
// types stay metric; only the text changes. Numbers follow the page language (`formatNumber`).
import { readonly, ref } from "vue";
import { formatNumber } from "@/i18n";
import { NONE } from "@/lib/format";
import { readStored, removeStored, writeStored } from "@/lib/storage";

export const UNITS_KEY = "units/non_metric";

// The same constants as neoaprs/units.py, and inHg and ft/min beside them.
const MILE_KM = 1.609344;
const FOOT_M = 0.3048;
const KNOT_KMH = 1.852;
const INCH_MM = 25.4;
const INHG_HPA = 33.8639;
const FPM_MS = 0.00508;
const MPH_KMH = MILE_KM;
/** Below 500 ft a distance is in feet. */
const FEET_BELOW_KM = 500 * FOOT_M * 0.001;

// The last value the daemon told is kept in the browser, so a page that loads draws in the
// station's units before the config arrives; the daemon's value always wins.
const on = ref(readStored(UNITS_KEY) === "true");
export const nonMetric = readonly(on);

/** Takes the switch from the config's values; `undefined` (no config) is metric. */
export function takeUnits(values: Readonly<Record<string, string>> | undefined): void {
  on.value = values?.[UNITS_KEY] === "true";
  if (values === undefined) removeStored(UNITS_KEY);
  else writeStored(UNITS_KEY, String(on.value));
}

/** `x` rounded to a multiple of `step`, never -0. */
function whole(x: number, step = 1): number {
  return Math.round(x / step) * step || 0;
}

/** `formatNumber` that writes a value which rounds to zero without a sign. */
function num(x: number, digits: number): string {
  return formatNumber(Math.abs(x) < 0.5 * 10 ** -digits ? 0 : x, digits);
}

/** One decimal under 10, whole above; rounded first, so 9.96 is "10", not "10.0". */
function tenthsOrWhole(x: number): string {
  const tenths = Math.round(x * 10) / 10;
  return tenths < 10 ? num(tenths, 1) : String(Math.round(x));
}

/** A distance as a table figure with no unit: km, or miles (never feet); a dash for none. */
export function distanceText(km: number | null): string {
  if (km === null) return NONE;
  return tenthsOrWhole(on.value ? km / MILE_KM : km);
}

/** The unit of `distanceText`, for a column head. */
export function distanceUnit(): string {
  return on.value ? "mi" : "km";
}

/** A distance with its unit: "8.2 km", "7.6 mi", under 500 ft "450 ft"; a dash for none. */
export function distanceWithUnit(km: number | null): string {
  if (km === null) return NONE;
  if (on.value && km < FEET_BELOW_KM) return `${whole(km / (FOOT_M * 0.001), 10)} ft`;
  return `${distanceText(km)} ${distanceUnit()}`;
}

/** A range in whole km or miles: "40 km", "25 mi". */
export function rangeText(km: number): string {
  return on.value ? `${whole(km / MILE_KM)} mi` : `${whole(km)} km`;
}

/** A height in whole metres or feet; a dash for none. */
export function heightText(m: number | null): string {
  if (m === null) return NONE;
  return on.value ? `${whole(m / FOOT_M)} ft` : `${whole(m)} m`;
}

/** A speed in whole km/h or mph; a dash for none. */
export function speedText(kmh: number | null): string {
  if (kmh === null) return NONE;
  return on.value ? `${whole(kmh / MPH_KMH)} mph` : `${whole(kmh)} km/h`;
}

/** An aircraft's altitude: whole metres, or feet to the nearest 25. */
export function aircraftAltitudeText(m: number | null): string {
  if (m === null) return NONE;
  return on.value ? `${whole(m / FOOT_M, 25)} ft` : `${whole(m)} m`;
}

/** An aircraft's speed: whole km/h, or whole knots. */
export function aircraftSpeedText(kmh: number | null): string {
  if (kmh === null) return NONE;
  return on.value ? `${whole(kmh / KNOT_KMH)} kn` : `${whole(kmh)} km/h`;
}

/** A ship's speed: whole km/h, or knots with one decimal under 10. */
export function shipSpeedText(kmh: number | null): string {
  if (kmh === null) return NONE;
  return on.value ? `${tenthsOrWhole(kmh / KNOT_KMH)} kn` : `${whole(kmh)} km/h`;
}

/**
 * A vertical speed with a sign (a real minus for descent): m/s with one decimal, or ft/min to the
 * nearest 50; level is "0 m/s", "0 ft/min".
 */
export function verticalText(ms: number | null): string {
  if (ms === null) return NONE;
  const size = on.value ? whole(Math.abs(ms) / FPM_MS, 50) : Math.round(Math.abs(ms) * 10) / 10;
  const unit = on.value ? "ft/min" : "m/s";
  if (size === 0) return `0 ${unit}`;
  return `${ms < 0 ? "\u2212" : "+"}${on.value ? String(size) : formatNumber(size, 1)} ${unit}`;
}

/** A temperature: °C with one decimal, or whole °F; a dash for none. */
export function tempText(c: number | null | undefined): string {
  if (c === null || c === undefined) return NONE;
  return on.value ? `${num(whole((c * 9) / 5 + 32), 0)} °F` : `${num(c, 1)} °C`;
}

/** Air pressure: hPa with one decimal, or inHg with two. */
export function pressureText(hpa: number | null): string {
  if (hpa === null) return NONE;
  return on.value ? `${num(hpa / INHG_HPA, 2)} inHg` : `${num(hpa, 1)} hPa`;
}

/** A storm's central pressure, whole hPa as sent, or inHg with two decimals. */
export function stormPressureText(hpa: number): string {
  return on.value ? pressureText(hpa) : `${whole(hpa)} hPa`;
}

/** Rain: mm with one decimal, or inches with two. */
export function rainText(mm: number | null): string {
  if (mm === null) return NONE;
  return on.value ? `${num(mm / INCH_MM, 2)} in` : `${num(mm, 1)} mm`;
}

/** Snow: mm with one decimal, or inches with one. */
export function snowText(mm: number | null): string {
  if (mm === null) return NONE;
  return on.value ? `${num(mm / INCH_MM, 1)} in` : `${num(mm, 1)} mm`;
}

/** The quantities of the trend graphs. */
export type ChartQuantity = "temp" | "pressure" | "wind" | "rain" | "speed";

interface ChartUnit {
  unit: string;
  of: (metric: number) => number;
  decimals: number;
  /** half the axis of a series with a single value */
  pad: number;
}

const METRIC_CHARTS: Record<ChartQuantity, ChartUnit> = {
  temp: { unit: "°C", of: (c) => c, decimals: 1, pad: 1 },
  pressure: { unit: "hPa", of: (hpa) => hpa, decimals: 1, pad: 1 },
  wind: { unit: "km/h", of: (kmh) => kmh, decimals: 1, pad: 1 },
  rain: { unit: "mm", of: (mm) => mm, decimals: 1, pad: 1 },
  speed: { unit: "km/h", of: (kmh) => kmh, decimals: 0, pad: 1 },
};

const OTHER_CHARTS: Record<ChartQuantity, ChartUnit> = {
  temp: { unit: "°F", of: (c) => (c * 9) / 5 + 32, decimals: 0, pad: 2 },
  pressure: { unit: "inHg", of: (hpa) => hpa / INHG_HPA, decimals: 2, pad: 0.03 },
  wind: { unit: "mph", of: (kmh) => kmh / MPH_KMH, decimals: 1, pad: 1 },
  rain: { unit: "in", of: (mm) => mm / INCH_MM, decimals: 2, pad: 0.04 },
  speed: { unit: "mph", of: (kmh) => kmh / MPH_KMH, decimals: 0, pad: 1 },
};

const chart = (q: ChartQuantity): ChartUnit => (on.value ? OTHER_CHARTS : METRIC_CHARTS)[q];

/** A metric reading of a graph in the units shown. */
export const chartValue = (q: ChartQuantity, metric: number): number => chart(q).of(metric);
export const chartUnit = (q: ChartQuantity): string => chart(q).unit;
/** The decimals of the graph's heading. */
export const chartDecimals = (q: ChartQuantity): number => chart(q).decimals;
/** How far the axis reaches either side of a series with one value. */
export const chartPad = (q: ChartQuantity): number => chart(q).pad;
