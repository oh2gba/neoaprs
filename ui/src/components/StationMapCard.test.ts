import "@/test/mockmap";
import { flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FakeMap, resetFakes } from "@/test/fakemap";
import { mountStationMap } from "@/test/stationmap";
import { NOW, ago, station, table } from "@/test/fixtures";
import { cssRule } from "@/test/css";

// A phone: a map 390 wide and 380 high with the card over its bottom, its top 130 px down.
const rect = (left: number, top: number, right: number, bottom: number): DOMRect => ({
  left,
  top,
  right,
  bottom,
  width: right - left,
  height: bottom - top,
  x: left,
  y: top,
  toJSON: () => ({}),
});

const stations = () =>
  table(
    station("OH2GBA", { is_me: true, lat: 60.17, lon: 24.94, symbol_code: "-" }),
    station("OH2PU-9", { lat: 60.2, lon: 24.65, last_position_at: ago(100) }),
    station("OH2RCH-2", { symbol_code: "#", lat: 60.3, lon: 25, heard_via: [], extensions: { phg: null, range_km: 20, dfs: null, df_bearing: null, area: null } }),
  );
const props = (extra = {}) => ({
  stations: stations(),
  selected: null,
  focus: null,
  home: { lat: 60.17, lon: 24.94 },
  now: NOW,
  dark: false,
  aging: { defaultMin: 0 },
  ...extra,
});

async function mounted(withCard = true) {
  const page = document.createElement("div");
  page.className = "mapwrap";
  if (withCard) page.innerHTML = '<section class="card"></section>';
  document.body.append(page);
  const { wrapper } = mountStationMap(props(), page);
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  resetFakes();
  localStorage.clear();
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(390);
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(380);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    return this.classList.contains("card") ? rect(10, 130, 380, 370) : rect(0, 0, 390, 380);
  });
});
afterEach(() => {
  vi.restoreAllMocks();
  document.body.replaceChildren();
});

describe("StationMap with the card of a station over it", () => {
  it("moves the map when the marker of the station picked is under the card, so that the marker is above the card", async () => {
    const wrapper = await mounted();
    FakeMap.last().screen = { x: 195, y: 190 };
    await wrapper.setProps({ selected: "OH2PU-9" });
    await flushPromises();
    expect(FakeMap.last().pans).toEqual([{ offset: [0, 100], options: { duration: 300 } }]);
  });

  it("leaves the map where it is when the marker is clear of the card, or when there is no card", async () => {
    const wrapper = await mounted();
    FakeMap.last().screen = { x: 195, y: 60 };
    await wrapper.setProps({ selected: "OH2PU-9" });
    await flushPromises();
    expect(FakeMap.last().pans).toEqual([]);
    document.body.replaceChildren();
    const bare = await mounted(false);
    FakeMap.last().screen = { x: 195, y: 190 };
    await bare.setProps({ selected: "OH2PU-9" });
    await flushPromises();
    expect(FakeMap.last().pans).toEqual([]);
  });

  it("does not move a map that is on its way somewhere", async () => {
    const wrapper = await mounted();
    FakeMap.last().screen = { x: 195, y: 190 };
    FakeMap.last().moving = true;
    await wrapper.setProps({ selected: "OH2PU-9" });
    await flushPromises();
    expect(FakeMap.last().pans).toEqual([]);
  });

  it("flies to a station so that it lands above the card, not under it", async () => {
    const wrapper = await mounted();
    await wrapper.setProps({ selected: "OH2PU-9", focus: { call: "OH2PU-9", n: 1 } });
    await flushPromises();
    expect(FakeMap.last().flights).toEqual([{ center: [24.65, 60.2], zoom: 11, offset: [0, -100] }]);
    expect(FakeMap.last().pans).toEqual([]);
  });

  it("fits itself to the range circle of a digipeater so that the circle lands above the card, with room for the offset", async () => {
    const wrapper = await mounted();
    await wrapper.setProps({ selected: "OH2RCH-2", focus: { call: "OH2RCH-2", n: 1 } });
    await flushPromises();
    expect(FakeMap.last().flights).toEqual([]);
    expect(FakeMap.last().pans).toEqual([]);
    expect(FakeMap.last().fits.map((fit) => fit.options)).toEqual([{ padding: { left: 40, right: 40, top: 140, bottom: 140 }, offset: [0, -100] }]);
  });

  it("has the card above the markers, which are in the map's own layer, and the map's buttons under it", () => {
    expect(cssRule(".stationmap")).toMatch(/z-index:\s*0/);
    expect(cssRule(".card")).toMatch(/z-index:\s*3/);
  });
});
