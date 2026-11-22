import { describe, expect, it, vi } from "vitest";
import { setLocale } from "@/i18n";
import {
  aircraftAltitudeText,
  aircraftSpeedText,
  chartDecimals,
  chartPad,
  chartUnit,
  chartValue,
  distanceText,
  distanceUnit,
  distanceWithUnit,
  heightText,
  nonMetric,
  pressureText,
  rainText,
  rangeText,
  shipSpeedText,
  snowText,
  speedText,
  stormPressureText,
  takeUnits,
  tempText,
  verticalText,
} from "@/lib/units";

const NON_METRIC = { "units/non_metric": "true" };
const MINUS = "\u2212";

/** Each formatter with its inputs and what it writes in metric and in the non-metric units. */
const TABLE: readonly { name: string; fn: (v: number | null) => string; rows: [number | null, string, string][] }[] = [
  {
    name: "distanceText (a table figure)",
    fn: distanceText,
    rows: [
      [12.3, "12", "7.6"],
      [8.24, "8.2", "5.1"],
      [16.03, "16", "10"],
      [0, "0.0", "0.0"],
      [-0.01, "0.0", "0.0"],
      [null, "-", "-"],
    ],
  },
  {
    name: "distanceWithUnit",
    fn: distanceWithUnit,
    rows: [
      [8.2, "8.2 km", "5.1 mi"],
      [10.4, "10 km", "6.5 mi"],
      [16.03, "16 km", "10 mi"],
      [0.3, "0.3 km", "0.2 mi"],
      [0.153, "0.2 km", "0.1 mi"],
      [0.152, "0.2 km", "500 ft"],
      [0.15, "0.2 km", "490 ft"],
      [0, "0.0 km", "0 ft"],
      [null, "-", "-"],
    ],
  },
  {
    name: "heightText",
    fn: heightText,
    rows: [
      [120.4, "120 m", "395 ft"],
      [6.1, "6 m", "20 ft"],
      [-10, "-10 m", "-33 ft"],
      [-0.1, "0 m", "0 ft"],
      [0, "0 m", "0 ft"],
      [null, "-", "-"],
    ],
  },
  {
    name: "speedText",
    fn: speedText,
    rows: [
      [85, "85 km/h", "53 mph"],
      [12.6, "13 km/h", "8 mph"],
      [-0.4, "0 km/h", "0 mph"],
      [0, "0 km/h", "0 mph"],
      [null, "-", "-"],
    ],
  },
  {
    name: "aircraftAltitudeText",
    fn: aircraftAltitudeText,
    rows: [
      [10973, "10973 m", "36000 ft"],
      [4892, "4892 m", "16050 ft"],
      [-3, "-3 m", "0 ft"],
      [0, "0 m", "0 ft"],
      [null, "-", "-"],
    ],
  },
  {
    name: "aircraftSpeedText",
    fn: aircraftSpeedText,
    rows: [
      [833.4, "833 km/h", "450 kn"],
      [0, "0 km/h", "0 kn"],
      [null, "-", "-"],
    ],
  },
  {
    name: "shipSpeedText",
    fn: shipSpeedText,
    rows: [
      [0.556, "1 km/h", "0.3 kn"],
      [22.96, "23 km/h", "12 kn"],
      [18.5, "19 km/h", "10 kn"],
      [0, "0 km/h", "0.0 kn"],
      [null, "-", "-"],
    ],
  },
  {
    name: "verticalText",
    fn: verticalText,
    rows: [
      [7.6, "+7.6 m/s", "+1500 ft/min"],
      [5.1, "+5.1 m/s", "+1000 ft/min"],
      [2.5, "+2.5 m/s", "+500 ft/min"],
      [1, "+1.0 m/s", "+200 ft/min"],
      [-3.3, `${MINUS}3.3 m/s`, `${MINUS}650 ft/min`],
      [0.1, "+0.1 m/s", "0 ft/min"],
      [-0.04, "0 m/s", "0 ft/min"],
      [0, "0 m/s", "0 ft/min"],
      [null, "-", "-"],
    ],
  },
  {
    name: "tempText",
    fn: tempText,
    rows: [
      [22.2, "22.2 °C", "72 °F"],
      [-40, "-40.0 °C", "-40 °F"],
      [-17.8, "-17.8 °C", "0 °F"],
      [-0.04, "0.0 °C", "32 °F"],
      [0, "0.0 °C", "32 °F"],
      [null, "-", "-"],
    ],
  },
  {
    name: "pressureText",
    fn: pressureText,
    rows: [
      [1013.2, "1013.2 hPa", "29.92 inHg"],
      [1028.4, "1028.4 hPa", "30.37 inHg"],
      [null, "-", "-"],
    ],
  },
  {
    name: "rainText",
    fn: rainText,
    rows: [
      [0.3, "0.3 mm", "0.01 in"],
      [25.4, "25.4 mm", "1.00 in"],
      [0, "0.0 mm", "0.00 in"],
      [null, "-", "-"],
    ],
  },
  {
    name: "snowText",
    fn: snowText,
    rows: [
      [25.4, "25.4 mm", "1.0 in"],
      [0, "0.0 mm", "0.0 in"],
      [null, "-", "-"],
    ],
  },
];

describe.each(TABLE)("$name", ({ fn, rows }) => {
  it.each(rows)("writes %s as %s, and as %s in the non-metric units", (value, metric, other) => {
    expect(fn(value)).toBe(metric);
    takeUnits(NON_METRIC);
    expect(fn(value)).toBe(other);
  });
});

describe("the texts with no null", () => {
  it("writes a range whole and a storm's pressure as sent or in inHg", () => {
    expect([rangeText(40.4), rangeText(0), stormPressureText(980)]).toEqual(["40 km", "0 km", "980 hPa"]);
    takeUnits(NON_METRIC);
    expect([rangeText(40), rangeText(0), stormPressureText(980)]).toEqual(["25 mi", "0 mi", "28.94 inHg"]);
  });
  it("names the unit of a distance column", () => {
    expect(distanceUnit()).toBe("km");
    takeUnits(NON_METRIC);
    expect(distanceUnit()).toBe("mi");
  });
});

describe("another language", () => {
  it("writes the decimal sign and the minus of the language", () => {
    setLocale("fi");
    takeUnits(NON_METRIC);
    expect([pressureText(1013.2), tempText(-40), distanceWithUnit(12.3), shipSpeedText(0.556)]).toEqual([
      "29,92 inHg",
      `${MINUS}40 °F`,
      "7,6 mi",
      "0,3 kn",
    ]);
  });
});

describe("the trend graphs", () => {
  it("convert the readings, and give each its unit, decimals and the reach of a flat axis", () => {
    const quantities = ["temp", "pressure", "wind", "rain", "speed"] as const;
    expect(quantities.map((q) => [chartUnit(q), chartDecimals(q), chartPad(q), chartValue(q, 10)])).toEqual([
      ["°C", 1, 1, 10],
      ["hPa", 1, 1, 10],
      ["km/h", 1, 1, 10],
      ["mm", 1, 1, 10],
      ["km/h", 0, 1, 10],
    ]);
    takeUnits(NON_METRIC);
    expect(quantities.map((q) => [chartUnit(q), chartDecimals(q), chartPad(q)])).toEqual([
      ["°F", 0, 2],
      ["inHg", 2, 0.03],
      ["mph", 1, 1],
      ["in", 2, 0.04],
      ["mph", 0, 1],
    ]);
    expect(chartValue("temp", 0)).toBe(32);
    expect(chartValue("pressure", 1013.25)).toBeCloseTo(29.921, 3);
    expect(chartValue("wind", 1.609344)).toBeCloseTo(1, 9);
    expect(chartValue("rain", 25.4)).toBeCloseTo(1, 9);
  });
});

describe("takeUnits", () => {
  it("is on only for the text true, and remembers what it was told", () => {
    takeUnits(NON_METRIC);
    expect(nonMetric.value).toBe(true);
    expect(localStorage.getItem("NeoAPRS.units/non_metric")).toBe("true");
    const others: Record<string, string>[] = [{ "units/non_metric": "false" }, { "units/non_metric": "x" }, {}];
    for (const values of others) {
      takeUnits(NON_METRIC);
      takeUnits(values);
      expect(nonMetric.value).toBe(false);
      expect(localStorage.getItem("NeoAPRS.units/non_metric")).toBe("false");
    }
    takeUnits(undefined);
    expect(nonMetric.value).toBe(false);
    expect(localStorage.getItem("NeoAPRS.units/non_metric")).toBeNull();
  });
  it("starts a page from the value it was told last, and metric when the browser keeps nothing", async () => {
    localStorage.setItem("NeoAPRS.units/non_metric", "true");
    vi.resetModules();
    expect((await import("@/lib/units")).nonMetric.value).toBe(true);
    localStorage.removeItem("NeoAPRS.units/non_metric");
    vi.resetModules();
    expect((await import("@/lib/units")).nonMetric.value).toBe(false);
  });
  it("starts metric when the browser's storage throws", async () => {
    const read = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.resetModules();
    expect((await import("@/lib/units")).nonMetric.value).toBe(false);
    read.mockRestore();
  });
});
