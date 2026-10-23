import { describe, expect, it } from "vitest";
import {
  arrowAngle,
  columnOf,
  hasValues,
  humidityText,
  isWeatherStation,
  markerWeather,
  pressureText,
  rainText,
  tempShort,
  tempText,
  windSpeedText,
} from "@/lib/weather";
import { NOW, ago, series, station, weather, weatherStation } from "@/test/fixtures";

describe("the readings as text", () => {
  it("writes each with its unit and a dash for none", () => {
    expect([tempText(10), tempText(-20.55), tempText(null), tempText(undefined)]).toEqual(["10.0 °C", "-20.6 °C", "-", "-"]);
    expect([pressureText(1028.4), pressureText(null)]).toEqual(["1028.4 hPa", "-"]);
    expect([humidityText(85), humidityText(null)]).toEqual(["85 %", "-"]);
    expect([windSpeedText(1.6), windSpeedText(0), windSpeedText(null)]).toEqual(["2 km/h", "0 km/h", "-"]);
    expect([rainText(0.3), rainText(null)]).toEqual(["0.3 mm", "-"]);
  });

  it("writes the temperature of a row narrowly, a dash for a station with no weather", () => {
    expect(tempShort(weatherStation())).toBe("10.0°");
    expect(tempShort(station("A"))).toBe("-");
    expect(tempShort(weatherStation("A", { weather: weather({ temp_c: null }) }))).toBe("-");
  });
});

describe("the wind arrow", () => {
  it("points where the wind goes, the way it comes from turned half a circle", () => {
    expect([arrowAngle(0), arrowAngle(90), arrowAngle(107), arrowAngle(180), arrowAngle(270), arrowAngle(360)]).toEqual([180, 270, 287, 0, 90, 180]);
    expect(arrowAngle(null)).toBeNull();
  });
});

describe("a weather station", () => {
  it("has the weather symbol or has sent weather", () => {
    expect(isWeatherStation(station("A", { symbol_code: "_" }))).toBe(true);
    expect(isWeatherStation(station("A", { weather: weather() }))).toBe(true);
    expect(isWeatherStation(station("A"))).toBe(false);
  });

  it("adds its temperature to the tooltip of its marker, and nothing to any other", () => {
    expect(markerWeather(weatherStation())).toBe(", 10.0 °C");
    expect(markerWeather(station("A"))).toBe("");
    expect(markerWeather(weatherStation("A", { weather: weather({ temp_c: null }) }))).toBe("");
  });
});

describe("the series", () => {
  it("is cut into the points of one column, the times in ms", () => {
    const s = series("OH2MUI", 24, 3);
    const temp = columnOf(s, "temp");
    expect(temp).toHaveLength(3);
    expect(temp[2]).toEqual({ t: NOW - 600_000, v: 10 });
    expect(columnOf(s, "pressure")[0]?.v).toBe(1020);
    expect(columnOf(s, "humidity")[1]?.v).toBe(80);
    expect(columnOf(s, "gust")[0]?.v).toBe(6);
  });

  it("keeps a missing value as null and has no points before the answer", () => {
    const s = { ...series("A", 24, 1), points: [[ago(60), null, null, null, null, null, null]] as ReturnType<typeof series>["points"] };
    expect(columnOf(s, "wind")).toEqual([{ t: NOW - 60_000, v: null }]);
    expect(hasValues(columnOf(s, "wind"))).toBe(false);
    expect(columnOf(null, "temp")).toEqual([]);
    expect(hasValues(columnOf(series("A", 24, 2), "temp"))).toBe(true);
  });
});
