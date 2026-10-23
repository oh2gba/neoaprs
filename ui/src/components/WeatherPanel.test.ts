import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import WeatherPanel from "@/components/WeatherPanel.vue";
import { NOW, series, station, weather, weatherStation } from "@/test/fixtures";

beforeEach(() => localStorage.clear());

function make(row = weatherStation(), answer: ReturnType<typeof series> | null = null) {
  return mount(WeatherPanel, { props: { row, series: answer, now: NOW } });
}

describe("WeatherPanel", () => {
  it("lays out the readings with how long ago they were heard", () => {
    const wrapper = make();
    expect(wrapper.find(".wx-temp").text()).toBe("10.0 °C");
    const text = wrapper.find(".wx-now").text();
    for (const wanted of ["2 km/h", "from 107° ESE", "gusts 2 km/h", "85 %", "1028.4 hPa", "0.3 mm", "4.1 mm", "3.3 mm", "10 min ago"])
      expect(text, wanted).toContain(wanted);
    expect(text).not.toContain("W/m²");
    expect(text).not.toContain("Snow");
  });

  it("turns the arrow to where the wind goes", () => {
    expect(make().find(".wx-arrow g").attributes("transform")).toBe("rotate(287)");
    const calm = make(weatherStation("A", { weather: weather({ wind_dir: null, wind_kmh: null, gust_kmh: null }) }));
    expect(calm.find("svg.wx-arrow").exists()).toBe(false);
    expect(calm.find(".wx-wind").text()).toContain("-");
  });

  it("shows luminosity and snow only when they were sent", () => {
    const text = make(weatherStation("A", { weather: weather({ luminosity: 72, snow_mm: 50.8 }) }))
      .find(".wx-values")
      .text();
    expect(text).toContain("72 W/m²");
    expect(text).toContain("50.8 mm");
  });

  it("says so for a weather station that has sent no weather, and still asks for its series", () => {
    const wrapper = make(station("OH2WX", { symbol_code: "_" }));
    expect(wrapper.find(".wx-none").text()).toBe("No weather report heard yet.");
    expect(wrapper.emitted("ask")).toEqual([["OH2WX", 24]]);
  });

  it("asks for the last 24 hours when it opens, and again when a new observation comes", async () => {
    const wrapper = make();
    expect(wrapper.emitted("ask")).toEqual([["OH2MUI", 24]]);
    await wrapper.setProps({ row: weatherStation("OH2MUI", {}, 5) });
    expect(wrapper.emitted("ask")).toEqual([
      ["OH2MUI", 24],
      ["OH2MUI", 24],
    ]);
    await wrapper.setProps({ row: weatherStation("OH2NJR", {}, 5) });
    expect(wrapper.emitted("ask")?.at(-1)).toEqual(["OH2NJR", 24]);
  });

  it("switches to 7 days, asks for 168 hours and remembers the choice", async () => {
    const wrapper = make();
    const buttons = wrapper.findAll(".wx-span button");
    expect(buttons.map((b) => b.attributes("aria-pressed"))).toEqual(["true", "false"]);
    await buttons[1]?.trigger("click");
    expect(wrapper.emitted("ask")?.at(-1)).toEqual(["OH2MUI", 168]);
    expect(buttons.map((b) => b.attributes("aria-pressed"))).toEqual(["false", "true"]);
    expect(make().emitted("ask")).toEqual([["OH2MUI", 168]]);
  });

  it("says it is loading until the answer for this station and span is there; another answer is not shown", async () => {
    const wrapper = make();
    expect(wrapper.text()).toContain("Loading the observations");
    await wrapper.setProps({ series: series("OH2NJR", 24, 5) });
    expect(wrapper.text()).toContain("Loading the observations");
    await wrapper.setProps({ series: series("OH2MUI", 168, 5) });
    expect(wrapper.text()).toContain("Loading the observations");
    expect(wrapper.findAll("figure")).toHaveLength(0);
  });

  it("draws the four graphs from the answer: temperature, pressure, wind with gusts and rain", () => {
    const wrapper = make(weatherStation(), series("OH2MUI", 24, 30));
    const titles = wrapper.findAll(".trend-head span:first-child").map((t) => t.text());
    expect(titles).toEqual(["Temperature", "Pressure", "Wind and gusts", "Rain, last hour"]);
    expect(wrapper.findAll("path.trend-band")).toHaveLength(1);
    expect(wrapper.findAll("rect.trend-bar").length).toBeGreaterThan(0);
  });

  it("leaves out the graph of a reading the station does not send, and says so when there is nothing at all", () => {
    const rows = series("OH2MUI", 24, 4);
    const bare = { ...rows, points: rows.points.map((p) => [p[0], p[1], null, null, null, null, null] as typeof p) };
    expect(make(weatherStation(), bare).findAll("figure")).toHaveLength(1);
    expect(make(weatherStation(), { ...rows, points: [] }).text()).toContain("No observations in this period.");
  });
});
