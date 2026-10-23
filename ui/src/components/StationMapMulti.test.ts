import "@/test/mockmap";
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import StationMap from "@/components/StationMap.vue";
import { FakeMap, FakeMarker, resetFakes } from "@/test/fakemap";
import { NOW, ago, station, table } from "@/test/fixtures";

const stations = () =>
  table(
    station("OH2GBA", { is_me: true, lat: 60.17, lon: 24.94, symbol_code: "-" }),
    station("OH2ZWA", { lat: 60.2, lon: 24.65, symbol_code: "_" }),
    station("OH2ZWB", { lat: 60.3, lon: 24.75, symbol_code: "_" }),
    station("OH2ZWC", { lat: 60.1, lon: 24.55, symbol_code: "_" }),
    station("OH2OLD", { lat: 60.4, lon: 25.1, last_position_at: ago(5 * 3600) }),
  );

async function mounted(extra = {}) {
  const wrapper = mount(StationMap, {
    props: {
      stations: stations(),
      selected: null,
      focus: null,
      home: { lat: 60.17, lon: 24.94 },
      now: NOW,
      dark: false,
      aging: { timeouts: new Map(), defaultMin: 60 },
      ...extra,
    },
    attachTo: document.body,
  });
  await flushPromises();
  return wrapper;
}
const markerOf = (call: string) => FakeMarker.live().find((m) => m.element.textContent === call);
const selected = (call: string) => markerOf(call)?.element.classList.contains("stn--selected") ?? false;
const click = (call: string, init: MouseEventInit = {}) => markerOf(call)?.element.dispatchEvent(new MouseEvent("click", { bubbles: true, ...init }));

beforeEach(() => {
  resetFakes();
  localStorage.clear();
});
afterEach(() => document.body.replaceChildren());

describe("StationMap with several cards", () => {
  it("says whether Ctrl (or Cmd on a Mac) was held when a marker was clicked", async () => {
    const wrapper = await mounted();
    click("OH2ZWA");
    click("OH2ZWB", { ctrlKey: true });
    click("OH2ZWC", { metaKey: true });
    expect(wrapper.emitted("select")).toEqual([
      ["OH2ZWA", false],
      ["OH2ZWB", true],
      ["OH2ZWC", true],
    ]);
  });

  it("lets go of the cards on a click on the map, but not on a Ctrl+click beside a marker", async () => {
    const wrapper = await mounted();
    FakeMap.last().fire("click", { originalEvent: new MouseEvent("click", { ctrlKey: true }) });
    expect(wrapper.emitted("select")).toBeUndefined();
    FakeMap.last().fire("click", { originalEvent: new MouseEvent("click") });
    expect(wrapper.emitted("select")).toEqual([[null]]);
  });

  it("marks the marker of every open card, the selected one and the others", async () => {
    const wrapper = await mounted({ selected: "OH2ZWC", others: ["OH2ZWA", "OH2ZWB"] });
    expect(["OH2ZWA", "OH2ZWB", "OH2ZWC", "OH2GBA"].map(selected)).toEqual([true, true, true, false]);
    await wrapper.setProps({ others: ["OH2ZWA"] });
    expect(["OH2ZWA", "OH2ZWB", "OH2ZWC"].map(selected)).toEqual([true, false, true]);
    await wrapper.setProps({ selected: null, others: [] });
    expect(["OH2ZWA", "OH2ZWC"].map(selected)).toEqual([false, false]);
  });

  it("shows the marker of a station past its timeout while its card is open, whichever card it is", async () => {
    const wrapper = await mounted();
    expect(markerOf("OH2OLD")).toBeUndefined();
    await wrapper.setProps({ selected: "OH2ZWA", others: ["OH2OLD"] });
    expect(selected("OH2OLD")).toBe(true);
    await wrapper.setProps({ others: [] });
    expect(markerOf("OH2OLD")).toBeUndefined();
  });

  it("makes the map the size of its box again when the box changes (the map is brought back from under the tab on a phone, or flies to a station that was picked there)", async () => {
    const wrapper = await mounted();
    const before = FakeMap.last().resizes;
    await wrapper.setProps({ focus: { call: "OH2ZWA", n: 1 } });
    expect(FakeMap.last().resizes).toBeGreaterThan(before);
  });
});
