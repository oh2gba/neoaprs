// The weather as the page writes and draws it: readings as text, the wind arrow's angle, and the
// `weather_series` message cut into the points of one graph.
import { NONE } from "@/lib/format";
import { extent, type Point } from "@/lib/chart";
import { chartPad, chartValue, tempText, type ChartQuantity } from "@/lib/units";
import type { StationRow, WeatherSeriesMessage } from "@/protocol/protocol";

/** The columns of a point after its time. */
type Column = "temp" | "pressure" | "wind" | "gust" | "rain" | "humidity";
const COLUMN_INDEX: Record<Column, number> = { temp: 1, pressure: 2, wind: 3, gust: 4, rain: 5, humidity: 6 };
const QUANTITY_OF: Partial<Record<Column, ChartQuantity>> = {
  temp: "temp",
  pressure: "pressure",
  wind: "wind",
  gust: "wind",
  rain: "rain",
};

/** One column of the series as points (time in ms, value in the units shown, or null). */
export function columnOf(series: WeatherSeriesMessage | null, column: Column): Point[] {
  const index = COLUMN_INDEX[column];
  const quantity = QUANTITY_OF[column];
  return (series?.points ?? []).map((point) => {
    const v = point[index] as number | null;
    return { t: Date.parse(point[0]), v: v === null || quantity === undefined ? v : chartValue(quantity, v) };
  });
}

/** The quantities with a graph each, for the axes cards share. */
type Quantity = "temp" | "wind" | "pressure" | "humidity" | "rain";
/** The lowest and highest value of each quantity, before the axis is rounded. */
export type Ranges = Partial<Record<Quantity, readonly [number, number]>>;

const SHARED: readonly { quantity: Quantity; columns: readonly Column[]; zero: boolean }[] = [
  { quantity: "temp", columns: ["temp"], zero: false },
  { quantity: "wind", columns: ["wind", "gust"], zero: true },
  { quantity: "pressure", columns: ["pressure"], zero: false },
  { quantity: "humidity", columns: ["humidity"], zero: false },
  { quantity: "rain", columns: ["rain"], zero: true },
];

/**
 * The value axis shared by several weather cards so curves compare at a glance: per quantity the
 * lowest and highest value over all series of `hours` (wind with gusts; wind and rain from 0).
 * A quantity no series has is left out.
 */
export function sharedRanges(all: readonly (WeatherSeriesMessage | null)[], hours: number): Ranges {
  const used = all.filter((series): series is WeatherSeriesMessage => series !== null && series.hours === hours);
  const out: Ranges = {};
  for (const { quantity, columns, zero } of SHARED) {
    const values = used.flatMap((series) =>
      columns.flatMap((column) => columnOf(series, column).flatMap((p) => (p.v === null ? [] : [p.v]))),
    );
    if (values.length > 0) out[quantity] = extent(values, zero, quantity === "humidity" ? 1 : chartPad(quantity));
  }
  return out;
}

/** Whether the column has at least one value. */
export function hasValues(points: readonly Point[]): boolean {
  return points.some((p) => p.v !== null);
}

/** A weather station: it has the weather symbol or has sent weather. */
export function isWeatherStation(row: StationRow): boolean {
  return row.weather !== null || row.symbol_code === "_";
}

export function humidityText(percent: number | null): string {
  return percent === null ? NONE : `${percent} %`;
}

/**
 * The angle to turn an up arrow so it points where the wind goes (wind direction is where it comes
 * from).
 */
export function arrowAngle(windDir: number | null): number | null {
  return windDir === null ? null : (windDir + 180) % 360;
}

/** What a marker tooltip adds for a weather station ("10.0 °C"); nothing for others. */
export function markerWeather(row: StationRow): string {
  return row.weather === null || row.weather.temp_c === null ? "" : tempText(row.weather.temp_c);
}
