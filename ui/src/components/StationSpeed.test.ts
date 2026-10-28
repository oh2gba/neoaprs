import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { nextTick, shallowRef } from "vue";
import StationCards from "@/components/StationCards.vue";
import type { SpeedSeriesMessage, StationRow } from "@/protocol/protocol";
import { fakeDaemon, withDaemon } from "@/test/context";
import { NOW, ago, station } from "@/test/fixtures";

afterEach(() => document.body.replaceChildren());

const car = station("OH2ZMA-9", { speed_kmh: 60, course_deg: 90 });
const fixed = station("OH2RDG", {
  track: [
    [ago(600), 60.2, 24.95],
    [ago(300), 60.2, 24.95],
  ],
});
const answer = (call: string): SpeedSeriesMessage => ({
  type: "speed_series",
  call,
  hours: 24,
  points: [
    [ago(3600), 40],
    [ago(1800), 80],
    [ago(60), 60],
  ],
});

function make(rows: StationRow[]) {
  const speeds = shallowRef<ReadonlyMap<string, SpeedSeriesMessage>>(new Map());
  const daemon = fakeDaemon({ now: NOW, speedSeriesByCall: speeds });
  const wrapper = mount(StationCards, { props: { rows, size: "desktop" }, global: withDaemon(daemon), attachTo: document.body });
  const asked = () => daemon.send.mock.calls.map(([c]) => c).filter((c) => c.cmd === "speed_series");
  return { wrapper, daemon, speeds, asked };
}

describe("the speed of a moving station on its card", () => {
  it("is asked for with the station's call when the card opens, and drawn as a line from the card's own answer, not another station's", async () => {
    const { wrapper, speeds, asked } = make([car]);
    expect(asked()).toEqual([{ cmd: "speed_series", call: "OH2ZMA-9", hours: 24 }]);
    const graph = () => wrapper.find("[data-speed]");
    expect(graph().find(".trend-head").text()).toContain("Speed, the last 24 hours");
    expect(graph().find(".trend-line").exists()).toBe(false);
    speeds.value = new Map([["OH2XYZ", answer("OH2XYZ")]]);
    await nextTick();
    expect(graph().find(".trend-line").exists()).toBe(false);
    speeds.value = new Map([...speeds.value, ["OH2ZMA-9", answer("OH2ZMA-9")]]);
    await nextTick();
    expect(graph().find(".trend-line").attributes("d")).toMatch(/^M/);
    expect(graph().find(".trend-read").text()).toMatch(/^60 km\/h\s+\d\d:\d\d:\d\d$/);
  });

  it("is asked for again when a new position of the station comes", async () => {
    const { wrapper, asked } = make([car]);
    await wrapper.setProps({ rows: [{ ...car, speed_kmh: 70 }] });
    expect(asked()).toHaveLength(1);
    await wrapper.setProps({ rows: [{ ...car, last_position_at: ago(5) }] });
    expect(asked()).toHaveLength(2);
  });

  it("has its frame before the answer comes, so the card does not grow when the line arrives", async () => {
    const { wrapper, speeds } = make([car]);
    const xs = () => wrapper.findAll("[data-speed] .tick").map((l) => l.attributes("x1"));
    const before = xs();
    expect(wrapper.findAll("[data-speed] svg")).toHaveLength(1);
    speeds.value = new Map([["OH2ZMA-9", answer("OH2ZMA-9")]]);
    await nextTick();
    expect(wrapper.findAll("[data-speed] svg")).toHaveLength(1);
    expect(xs()).toEqual(before);
  });

  it("is not on the card of a fixed station, nor of our own station moving, and nothing is asked for them", () => {
    const { wrapper, asked } = make([fixed, station("OH2GBA", { is_me: true, speed_kmh: 50 })]);
    expect(wrapper.findAll(".card")).toHaveLength(2);
    expect(wrapper.find("[data-speed]").exists()).toBe(false);
    expect(asked()).toEqual([]);
  });
});
