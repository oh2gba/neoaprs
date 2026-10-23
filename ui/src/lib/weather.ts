// The weather as the page writes it and draws it: the readings as text, the wind arrow's angle, and the series of the daemon's `weather_series` message cut into the points of one graph.
import { formatNumber } from "@/i18n";
import { NONE } from "@/lib/format";
import { extent, type Point } from "@/lib/chart";
import type { StationRow, WeatherSeriesMessage } from "@/protocol/protocol";

/** The columns of a point of the message after its time. */
type Column = "temp" | "pressure" | "wind" | "gust" | "rain" | "humidity";
const COLUMN_INDEX: Record<Column, number> = { temp: 1, pressure: 2, wind: 3, gust: 4, rain: 5, humidity: 6 };

/** One column of the series as points (time in ms, value or null). */
export function columnOf(series: WeatherSeriesMessage | null, column: Column): Point[] {
  const index = COLUMN_INDEX[column];
  return (series?.points ?? []).map((point) => ({ t: Date.parse(point[0]), v: point[index] as number | null }));
}

/** The quantities of a weather card that have a graph each, for the axes that cards share. */
type Quantity = "temp" | "wind" | "pressure" | "humidity" | "rain";
/** The span of values of each quantity (the lowest and the highest, before the axis is rounded to round numbers). */
export type Ranges = Partial<Record<Quantity, readonly [number, number]>>;

const SHARED: readonly { quantity: Quantity; columns: readonly Column[]; zero: boolean }[] = [
  { quantity: "temp", columns: ["temp"], zero: false },
  { quantity: "wind", columns: ["wind", "gust"], zero: true },
  { quantity: "pressure", columns: ["pressure"], zero: false },
  { quantity: "humidity", columns: ["humidity"], zero: false },
  { quantity: "rain", columns: ["rain"], zero: true },
];

/** The value axis that several weather cards share, so that their curves can be compared at a glance: for each quantity the lowest and the highest value of all the series of the span `hours` (the wind with its gusts, the wind and the rain from 0); a quantity no series has is left out. */
export function sharedRanges(all: readonly (WeatherSeriesMessage | null)[], hours: number): Ranges {
  const used = all.filter((series): series is WeatherSeriesMessage => series !== null && series.hours === hours);
  const out: Ranges = {};
  for (const { quantity, columns, zero } of SHARED) {
    const values = used.flatMap((series) => columns.flatMap((column) => columnOf(series, column).flatMap((p) => (p.v === null ? [] : [p.v]))));
    if (values.length > 0) out[quantity] = extent(values, zero);
  }
  return out;
}

/** True when the column has at least one value. */
export function hasValues(points: readonly Point[]): boolean {
  return points.some((p) => p.v !== null);
}

/** A station the page draws as a weather station: its symbol is the weather symbol, or it has sent weather. */
export function isWeatherStation(row: StationRow): boolean {
  return row.weather !== null || row.symbol_code === "_";
}

export function tempText(c: number | null | undefined): string {
  return c === null || c === undefined ? NONE : `${formatNumber(c, 1)} °C`;
}

export function pressureText(hpa: number | null): string {
  return hpa === null ? NONE : `${formatNumber(hpa, 1)} hPa`;
}

export function humidityText(percent: number | null): string {
  return percent === null ? NONE : `${percent} %`;
}

export function windSpeedText(kmh: number | null): string {
  return kmh === null ? NONE : `${Math.round(kmh)} km/h`;
}

export function rainText(mm: number | null): string {
  return mm === null ? NONE : `${formatNumber(mm, 1)} mm`;
}

/** The angle to turn an arrow that points up so that it points where the wind goes: the direction is where it comes from. Null when there is no direction. */
export function arrowAngle(windDir: number | null): number | null {
  return windDir === null ? null : (windDir + 180) % 360;
}

/** What a marker's tooltip adds for a weather station: "10.0 °C"; nothing for any other. */
export function markerWeather(row: StationRow): string {
  return row.weather === null || row.weather.temp_c === null ? "" : tempText(row.weather.temp_c);
}
