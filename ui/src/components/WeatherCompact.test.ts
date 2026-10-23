import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import TrendChart from "@/components/TrendChart.vue";
import WeatherCompact from "@/components/WeatherCompact.vue";
import { NOW, series, weatherStation } from "@/test/fixtures";

beforeEach(() => localStorage.clear());
const row = weatherStation("OH2ZWA");
const make = (extra: Record<string, unknown> = {}) => mount(WeatherCompact, { props: { row, series: series("OH2ZWA", 24, 12), now: NOW, ...extra } });
const yLabels = (wrapper: ReturnType<typeof make>) => wrapper.findAll(".trend").map((t) => t.findAll(".trend-grid > g > text").map((x) => x.text()));

describe("WeatherCompact", () => {
  it("has the readings in one line: the temperature, the wind with its gusts, the humidity, the pressure, and how long ago", () => {
    const text = make().find(".wx-line").text();
    for (const wanted of ["10.0 °C", "2 km/h ESE (2)", "85 %", "1028.4 hPa", "ago"]) expect(text).toContain(wanted);
    expect(make().find(".wx-span").exists()).toBe(false);
  });

  it("asks the daemon for the series of the span when it opens, and again for a new observation", async () => {
    const wrapper = make();
    expect(wrapper.emitted("ask")).toEqual([["OH2ZWA", 24]]);
    await wrapper.setProps({ row: { ...row, weather_at: "2026-10-21T12:30:00Z" } });
    expect(wrapper.emitted("ask")).toHaveLength(2);
  });

  it("draws a small graph, half a card wide, for each quantity the station sends: temperature, wind, pressure, humidity and rain, two side by side", () => {
    const wrapper = make();
    expect(wrapper.findAll(".trend.compact").map((t) => t.find("figcaption span").text())).toEqual(["Temperature", "Wind", "Pressure", "Humidity", "Rain 1 h"]);
    expect(wrapper.findAll(".trend.compact svg").every((svg) => svg.attributes("viewBox")?.startsWith("0 0 160 "))).toBe(true);
  });

  it("leaves out a graph the station does not send, and says so while the observations have not come", () => {
    const sparse = series("OH2ZWA", 24, 6);
    sparse.points = sparse.points.map((p) => [p[0], p[1], null, null, null, null, null]);
    expect(
      make({ series: sparse })
        .findAll(".trend")
        .map((t) => t.find("figcaption span").text()),
    ).toEqual(["Temperature"]);
    expect(make({ series: null }).text()).toContain("Loading the observations");
    expect(make({ series: null }).findAll(".trend")).toHaveLength(0);
  });

  it("has the hours under the last row only (the last two graphs of an even number, the last one of an odd), and each graph 44 to 56 px high", () => {
    const wrapper = make();
    const labelled = wrapper.findAll(".trend").map((t) => t.findAll(".trend-grid text").some((x) => /^\d\d:00$/.test(x.text())));
    expect(labelled).toEqual([false, false, false, false, true]);
    const heights = wrapper.findAll(".trend svg").map((svg) => Number(svg.attributes("viewBox")?.split(" ")[3]));
    expect(heights).toEqual([44, 44, 44, 44, 56]);
    const norain = series("OH2ZWA", 24, 12);
    norain.points = norain.points.map((p) => [p[0], p[1], p[2], p[3], p[4], null, p[6]]);
    const four = make({ series: norain });
    expect(four.findAll(".trend").map((t) => t.findAll(".trend-grid text").some((x) => /^\d\d:00$/.test(x.text())))).toEqual([false, false, true, true]);
  });

  it("draws every graph on the axis it is given, so that cards can share one", () => {
    const own = make();
    const shared = make({ ranges: { temp: [-20, 40], pressure: [980, 1040] } });
    expect(yLabels(shared)[0]).not.toEqual(yLabels(own)[0]);
    expect(yLabels(shared)[0]?.[0]).toBe("-20");
    expect(yLabels(shared)[0]?.at(-1)).toMatch(/^40/);
    expect(yLabels(shared)[2]?.[0]).toBe("980");
    expect(yLabels(shared)[1]).toEqual(yLabels(own)[1]); // (no range given for the wind: its own)
  });

  it("is of the span of the graphs of every card, which is 24 hours or the week", () => {
    localStorage.setItem("NeoAPRS.wxhours", "168");
    const wrapper = mount(WeatherCompact, { props: { row, series: series("OH2ZWA", 168, 12), now: NOW } });
    expect(wrapper.emitted("ask")).toEqual([["OH2ZWA", 168]]);
    expect(wrapper.findAllComponents(TrendChart)[0]?.props("to")).toBeGreaterThan(
      (wrapper.findAllComponents(TrendChart)[0]?.props("from") as number) + 167 * 3_600_000,
    );
  });

  it("says so when no weather report has been heard", () => {
    const none = weatherStation("OH2ZWA", { weather: null, weather_at: null });
    expect(make({ row: none }).text()).toContain("No weather report heard yet");
  });
});
