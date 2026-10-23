import "@/test/mockmap";
import { flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FakeMap, FakeMarker, resetFakes } from "@/test/fakemap";
import { mountStationMap } from "@/test/stationmap";
import { NOW, ago, station, table, weather } from "@/test/fixtures";

const stations = () =>
  table(
    station("OH2GBA", { is_me: true, lat: 60.17, lon: 24.94, symbol_code: "-" }),
    station("OH2PU-9", {
      lat: 60.2,
      lon: 24.65,
      last_heard: ago(120),
      last_status: "On the road",
      last_comment: "Going home",
      distance_km: 21,
      bearing_deg: 270,
      last_route: "via OH2RCH-2",
    }),
    station("OH2MUI", { lat: 60.3, lon: 25.1, last_route: "direct", symbol_code: "_", weather: weather({ temp_c: 10 }) }),
  );
const props = (extra = {}) => ({
  stations: stations(),
  selected: null,
  focus: null,
  home: { lat: 60.17, lon: 24.94 },
  now: NOW,
  dark: false,
  aging: { timeouts: new Map(), defaultMin: 0 },
  ...extra,
});
const markerOf = (call: string) => FakeMarker.live().find((m) => m.element.textContent === call)?.element as HTMLElement;
const card = () => document.querySelector<HTMLElement>(".hovercard");
const shown = () => card() !== null && !card()?.hidden;

function pointer(target: HTMLElement, type: string, pointerType = "mouse"): void {
  const event = new Event(type);
  Object.defineProperty(event, "pointerType", { value: pointerType });
  target.dispatchEvent(event);
}

async function mounted(extra = {}) {
  const { wrapper } = mountStationMap(props(extra));
  await flushPromises();
  vi.useFakeTimers();
  return wrapper;
}

beforeEach(() => {
  resetFakes();
  localStorage.clear();
});
afterEach(() => {
  vi.useRealTimers();
  document.body.replaceChildren();
});

describe("the card of a station under the pointer", () => {
  it("comes after a short delay, with the main facts of the station", async () => {
    await mounted();
    pointer(markerOf("OH2PU-9"), "pointerenter");
    expect(shown()).toBe(false);
    vi.advanceTimersByTime(200);
    expect(shown()).toBe(false);
    vi.advanceTimersByTime(60);
    expect(shown()).toBe(true);
    const text = card()?.textContent ?? "";
    for (const part of ["OH2PU-9", "Car", "2 min ago", "On the road", "Going home", "21 km, 270° W", "via OH2RCH-2"]) expect(text).toContain(part);
  });

  it("says heard direct and the temperature of a weather station", async () => {
    await mounted();
    pointer(markerOf("OH2MUI"), "pointerenter");
    vi.advanceTimersByTime(300);
    expect(card()?.textContent).toContain("heard direct");
    expect(card()?.textContent).toContain("10.0 °C");
    expect(card()?.textContent).not.toContain("Status");
  });

  it("is one element for all the markers, which goes when the pointer leaves", async () => {
    await mounted();
    pointer(markerOf("OH2PU-9"), "pointerenter");
    vi.advanceTimersByTime(300);
    pointer(markerOf("OH2PU-9"), "pointerleave");
    expect(shown()).toBe(false);
    pointer(markerOf("OH2MUI"), "pointerenter");
    vi.advanceTimersByTime(300);
    expect(document.querySelectorAll(".hovercard")).toHaveLength(1);
    expect(card()?.textContent).toContain("OH2MUI");
  });

  it("does not come when the pointer is gone before the delay", async () => {
    await mounted();
    pointer(markerOf("OH2PU-9"), "pointerenter");
    vi.advanceTimersByTime(100);
    pointer(markerOf("OH2PU-9"), "pointerleave");
    vi.advanceTimersByTime(500);
    expect(shown()).toBe(false);
  });

  it("is not there for a finger: a tap only opens the station", async () => {
    const wrapper = await mounted();
    pointer(markerOf("OH2PU-9"), "pointerenter", "touch");
    vi.advanceTimersByTime(1000);
    expect(shown()).toBe(false);
    markerOf("OH2PU-9").click();
    expect(wrapper.emitted("select")).toEqual([["OH2PU-9", false]]);
  });

  it("goes with a click, which still selects the station", async () => {
    const wrapper = await mounted();
    pointer(markerOf("OH2PU-9"), "pointerenter");
    vi.advanceTimersByTime(300);
    markerOf("OH2PU-9").click();
    expect(shown()).toBe(false);
    expect(wrapper.emitted("select")).toEqual([["OH2PU-9", false]]);
  });

  it("goes when the map moves and when the station is gone, and follows the station's row", async () => {
    const wrapper = await mounted();
    pointer(markerOf("OH2PU-9"), "pointerenter");
    vi.advanceTimersByTime(300);
    const changed = stations();
    changed.set("OH2PU-9", station("OH2PU-9", { lat: 60.2, lon: 24.65, last_status: "Parked" }));
    await wrapper.setProps({ stations: changed });
    expect(card()?.textContent).toContain("Parked");
    FakeMap.last().fire("movestart");
    expect(shown()).toBe(false);
    pointer(markerOf("OH2PU-9"), "pointerenter");
    vi.advanceTimersByTime(300);
    const without = stations();
    without.delete("OH2PU-9");
    await wrapper.setProps({ stations: without });
    expect(shown()).toBe(false);
  });

  it("is built from text, never markup, and is taken away with the map", async () => {
    const rows = stations();
    rows.set("OH2PU-9", station("OH2PU-9", { lat: 60.2, lon: 24.65, last_comment: "<img src=x>" }));
    const wrapper = await mounted({ stations: rows });
    pointer(markerOf("OH2PU-9"), "pointerenter");
    vi.advanceTimersByTime(300);
    expect(card()?.querySelector("img")).toBeNull();
    expect(card()?.textContent).toContain("<img src=x>");
    wrapper.unmount();
    expect(card()).toBeNull();
  });
});
