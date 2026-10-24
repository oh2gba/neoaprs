import "@/test/mockmap";
import { flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FakeMap, resetFakes } from "@/test/fakemap";
import { mountStationMap } from "@/test/stationmap";
import { NOW, ago, station, table } from "@/test/fixtures";

// A map 390 wide and 380 high with a card of the row over its bottom (10, 130 to 380, 370), and a card the user has moved to its top left (20, 20 to 150, 100).
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

async function mounted(cards: string) {
  const page = document.createElement("div");
  page.className = "mapwrap";
  page.innerHTML = cards;
  document.body.append(page);
  const { wrapper } = mountStationMap(props(), page);
  await flushPromises();
  return wrapper;
}
const ROW = '<section class="card"></section>';
const MOVED = '<section class="card moved"></section>';

beforeEach(() => {
  resetFakes();
  localStorage.clear();
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(390);
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(380);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    if (this.classList.contains("moved")) return rect(20, 20, 150, 100);
    return this.classList.contains("card") ? rect(10, 130, 380, 370) : rect(0, 0, 390, 380);
  });
});
afterEach(() => {
  vi.restoreAllMocks();
  document.body.replaceChildren();
});

describe("StationMap with a card the user has moved", () => {
  it("keeps the marker clear of the moved card where it really stands: a marker under it is moved to its side", async () => {
    const wrapper = await mounted(MOVED);
    FakeMap.last().screen = { x: 80, y: 60 };
    await wrapper.setProps({ selected: "OH2PU-9" });
    await flushPromises();
    expect(FakeMap.last().pans).toEqual([{ offset: [-110, 0], options: { duration: 300 } }]); // (there is no room above it: beside it, 40 px from its right edge)
  });

  it("does not take the moved card for part of the row: a marker between the two is left where it is", async () => {
    const wrapper = await mounted(ROW + MOVED);
    FakeMap.last().screen = { x: 250, y: 60 };
    await wrapper.setProps({ selected: "OH2PU-9" });
    await flushPromises();
    expect(FakeMap.last().pans).toEqual([]);
  });

  it("still moves a marker that is under the row of cards, above it, with a moved card elsewhere", async () => {
    const wrapper = await mounted(ROW + MOVED);
    FakeMap.last().screen = { x: 195, y: 190 };
    await wrapper.setProps({ selected: "OH2PU-9" });
    await flushPromises();
    expect(FakeMap.last().pans).toEqual([{ offset: [0, 100], options: { duration: 300 } }]);
  });

  it("flies to a station so that it lands clear of the moved card: the middle of the map is not under it, so it flies straight", async () => {
    const wrapper = await mounted(MOVED);
    await wrapper.setProps({ selected: "OH2PU-9", focus: { call: "OH2PU-9", n: 1 } });
    await flushPromises();
    expect(FakeMap.last().flights).toEqual([{ center: [24.65, 60.2], zoom: 11 }]);
  });

  it("flies to a station so that it lands clear of a moved card that is over the middle of the map", async () => {
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      return this.classList.contains("moved") ? rect(100, 120, 290, 260) : rect(0, 0, 390, 380);
    });
    const wrapper = await mounted(MOVED);
    await wrapper.setProps({ selected: "OH2PU-9", focus: { call: "OH2PU-9", n: 1 } });
    await flushPromises();
    expect(FakeMap.last().flights).toEqual([{ center: [24.65, 60.2], zoom: 11, offset: [135, 0] }]); // (the middle, 195/190, goes to 40 px right of the card's right edge, 330)
  });
});
