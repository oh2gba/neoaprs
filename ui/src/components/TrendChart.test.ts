import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import TrendChart from "@/components/TrendChart.vue";
import type { Point } from "@/lib/chart";

const HOUR = 3_600_000;
const TO = Date.parse("2026-10-21T12:00:00Z");
const FROM = TO - 24 * HOUR;
const at = (hoursAgo: number, v: number | null): Point => ({ t: TO - hoursAgo * HOUR, v });
const temps = [at(20, 4), at(15, 6), at(10, 9), at(5, 8), at(1, 7)];

function make(props: Record<string, unknown> = {}) {
  return mount(TrendChart, { props: { title: "Temperature", unit: "°C", from: FROM, to: TO, main: temps, tone: "temp", ...props } });
}

describe("TrendChart", () => {
  it("draws the series as a path in the tone of the chart, with ticks on both axes", () => {
    const wrapper = make();
    expect(wrapper.classes()).toContain("tone-temp");
    expect(wrapper.find("path.trend-line").attributes("d")).toMatch(/^M[\d.]+,[\d.]+C/);
    const labels = wrapper.findAll("text").map((t) => t.text());
    expect(labels).toEqual(expect.arrayContaining(["4", "6", "8", "10"]));
    expect(labels.some((l) => /^\d\d:00$/.test(l))).toBe(true);
    expect(wrapper.find("svg").attributes("role")).toBe("img");
  });

  it("says the newest value and its time in the heading until the pointer is over the graph", () => {
    const wrapper = make();
    expect(wrapper.find(".trend-read").text()).toMatch(/^7\.0 °C {2}\d\d:\d\d:\d\d$/);
    expect(wrapper.find(".trend-cursor").exists()).toBe(false);
  });

  it("shows a line, a dot and the value and time of the nearest observation under the pointer, and takes them away when it leaves", async () => {
    const wrapper = make();
    const svg = wrapper.find("svg");
    svg.element.getBoundingClientRect = () => ({ left: 0, width: 320, top: 0, height: 100, right: 320, bottom: 100, x: 0, y: 0, toJSON: () => ({}) });
    await svg.trigger("pointermove", { clientX: 36 + ((TO - 10 * HOUR - FROM) / (24 * HOUR)) * 278 + 2 }); // the plot is 278 wide from 36: just right of the observation 10 h ago
    expect(wrapper.find(".trend-cursor").exists()).toBe(true);
    expect(wrapper.find(".trend-dot").exists()).toBe(true);
    expect(wrapper.find(".trend-read").text()).toMatch(/^9\.0 °C {2}\d\d:\d\d:\d\d$/);
    await svg.trigger("pointerleave");
    expect(wrapper.find(".trend-cursor").exists()).toBe(false);
    expect(wrapper.find(".trend-read").text()).toMatch(/^7\.0 °C {2}\d\d:\d\d:\d\d$/);
  });

  it("draws the gusts as a lighter band and line over the sustained wind, from zero", () => {
    const wind = [at(3, 2), at(2, 4), at(1, 3)];
    const gust = [at(3, 5), at(2, 9), at(1, 6)];
    const wrapper = make({ title: "Wind and gusts", unit: "km/h", main: wind, band: gust, zero: true, tone: "wind" });
    expect(wrapper.find("path.trend-band").attributes("d")).toMatch(/Z$/);
    expect(wrapper.find("path.trend-upper").exists()).toBe(true);
    expect(wrapper.findAll("text").map((t) => t.text())).toContain("0");
  });

  it("draws the rain as bars standing on zero and no line", () => {
    const rain = [at(5, 0), at(4, 0.3), at(3, 1.2), at(2, 0), at(1, 0.5)];
    const wrapper = make({ title: "Rain", unit: "mm", main: rain, asBars: true, zero: true, tone: "rain" });
    expect(wrapper.findAll("rect.trend-bar")).toHaveLength(3);
    expect(wrapper.find("path.trend-line").exists()).toBe(false);
  });

  it("carries the line on across the hours the station was silent, as one curve", () => {
    const quiet = [at(20, 4), at(19.8, 5), at(3, 6), at(2.8, 7)];
    const d = make({ main: quiet }).find("path.trend-line").attributes("d") ?? "";
    expect(d.match(/M/g)).toHaveLength(1);
    expect(d.match(/C/g)).toHaveLength(3);
  });

  it("draws a single reading as a dot and a series with no value as a frame only", () => {
    expect(
      make({ main: [at(3, null), at(2, 5)] })
        .find("path.trend-line")
        .attributes("d"),
    ).toMatch(/h0$/);
    const empty = make({ main: [at(3, null)] });
    expect(empty.find("path.trend-line").exists()).toBe(false);
    expect(empty.find(".trend-read").text()).toBe("");
  });

  it("leaves a bar out for an hour with no reading and draws no curve for the rain", () => {
    const rain = [at(5, 0.4), at(4, null), at(3, null), at(2, 1)];
    const wrapper = make({ title: "Rain", unit: "mm", main: rain, asBars: true, zero: true, tone: "rain" });
    expect(wrapper.findAll("rect.trend-bar")).toHaveLength(2);
    expect(wrapper.find("path.trend-line").exists()).toBe(false);
  });
});
