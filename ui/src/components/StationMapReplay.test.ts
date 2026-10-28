import "@/test/mockmap";
import { flushPromises, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FakeMap, FakeMarker, resetFakes } from "@/test/fakemap";
import { mountStationMap } from "@/test/stationmap";
import { NOW, station, table } from "@/test/fixtures";
import { ROUTE_LAYERS } from "@/lib/routelayers";
import { TRACK_LAYERS } from "@/lib/tracklayers";
import type { PositionHistoryMessage } from "@/protocol/protocol";

const START = "2026-10-21T09:00:00Z";
const T0 = Date.parse(START);
const at = (minutes: number): string => new Date(T0 + minutes * 60_000).toISOString().replace(".000", "");

const props = (extra = {}) => ({
  stations: table(station("OH2GBA", { is_me: true, lat: 60.17, lon: 24.94 }), station("OH2RDG-9", { lat: 60.5, lon: 25.5, symbol_code: ">" })),
  selected: null,
  focus: null,
  home: { lat: 60.17, lon: 24.94 },
  now: NOW,
  dark: false,
  aging: { defaultMin: 0 },
  ...extra,
});

const answer: PositionHistoryMessage = {
  type: "position_history",
  hours: 3,
  start: START,
  end: at(180),
  stations: {
    "OH2RDG-9": [
      [at(0), 60.0, 25.0],
      [at(2), 60.02, 25.0],
    ],
    LEADER: [[at(60), 60.3, 24.7]],
  },
};

const replayMarkers = () => FakeMarker.live().filter((m) => m.element.classList.contains("stn--replay"));
const liveLayers = [...TRACK_LAYERS, ...ROUTE_LAYERS];

const mounts: VueWrapper[] = [];

async function mounted(extra = {}) {
  const { wrapper, daemon } = mountStationMap(props(extra));
  mounts.push(wrapper); // (unmounted after the test: the replay's timer goes with the map)
  await flushPromises();
  FakeMap.last().fire("style.load");
  return { wrapper, daemon };
}

beforeEach(() => {
  resetFakes();
  localStorage.clear();
});
afterEach(() => {
  for (const wrapper of mounts.splice(0)) wrapper.unmount();
  vi.useRealTimers();
  document.body.replaceChildren();
});

describe("the replay of the map", () => {
  it("is the last item of the map's menu, which asks the page to open it", async () => {
    const { wrapper } = await mounted();
    FakeMap.last().fire("contextmenu", { lngLat: { lat: 60.1, lng: 24.9 }, point: { x: 1, y: 1 }, originalEvent: new MouseEvent("contextmenu") });
    await flushPromises();
    document.querySelector<HTMLElement>(".mapmenu [data-item='replay']")?.click();
    await flushPromises();
    expect(wrapper.emitted("replay")).toEqual([[true]]);
  });

  it("asks for the span, hides the live map and plays the stations where they were, with their trails", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] });
    const { wrapper, daemon } = await mounted();
    const map = FakeMap.last();
    expect(liveLayers.every((id) => map.layers.includes(id))).toBe(true);
    await wrapper.setProps({ replay: true });
    expect(daemon.send).toHaveBeenCalledWith({ cmd: "position_history", hours: 3 });
    expect(wrapper.find(".stationmap").classes()).toContain("replaying");
    expect(wrapper.find(".replaybar").exists()).toBe(true);
    expect(liveLayers.map((id) => map.visibility.get(id))).toEqual(liveLayers.map(() => "none"));
    daemon.positionHistory.value = answer;
    await flushPromises();
    expect(replayMarkers().map((m) => [m.element.textContent, m.lngLat])).toEqual([["OH2RDG-9", [25.0, 60.0]]]);
    expect(replayMarkers()[0]?.element.querySelector(".stn-icon")?.classList.contains("stn-plain")).toBe(false); // (the symbol the station book has)
    vi.advanceTimersByTime(1000); // (five minutes of the span)
    await flushPromises();
    expect(replayMarkers()[0]?.lngLat).toEqual([25.0, 60.02]);
    const trails = map.getSource("replay-trails")?.setData.mock.calls.at(-1)?.[0] as { features: { geometry: { coordinates: number[][] } }[] };
    expect(trails.features[0]?.geometry.coordinates).toEqual([
      [25.0, 60.0],
      [25.0, 60.02],
    ]);
    vi.advanceTimersByTime(12_000); // (an hour)
    await flushPromises();
    expect(replayMarkers().map((m) => m.element.textContent)).toEqual(["OH2RDG-9", "LEADER"]);
    expect(replayMarkers()[1]?.element.querySelector(".stn-icon")?.classList.contains("stn-plain")).toBe(true); // (not in the station book now)
  });

  it("brings the live map back as it was when it closes, and its cross asks the page to close it", async () => {
    const { wrapper, daemon } = await mounted({ replay: true });
    const map = FakeMap.last();
    daemon.positionHistory.value = answer;
    await flushPromises();
    expect(replayMarkers()).toHaveLength(1);
    await wrapper.find(".replay-close").trigger("click");
    expect(wrapper.emitted("replay")).toEqual([[false]]);
    await wrapper.setProps({ replay: false });
    expect(replayMarkers()).toEqual([]);
    expect(wrapper.find(".stationmap").classes()).not.toContain("replaying");
    expect(wrapper.find(".replaybar").exists()).toBe(false);
    expect(liveLayers.map((id) => map.visibility.get(id))).toEqual(liveLayers.map(() => "visible"));
    expect(FakeMarker.live().map((m) => m.element.textContent)).toEqual(["OH2GBA", "OH2RDG-9"]);
    expect((map.getSource("replay-trails")?.setData.mock.calls.at(-1)?.[0] as { features: unknown[] }).features).toEqual([]);
  });

  it("hides the live layers again when the style is set again (the colour scheme changed)", async () => {
    await mounted({ replay: true });
    const map = FakeMap.last();
    map.visibility.clear();
    map.fire("style.load");
    expect(map.visibility.get("tracks-line")).toBe("none");
  });

  it("says so when no station was heard in the span", async () => {
    const { daemon } = await mounted({ replay: true });
    daemon.positionHistory.value = { ...answer, stations: {} };
    await flushPromises();
    expect(daemon.say).toHaveBeenCalledWith("No positions were heard in the last 3 h");
  });
});
