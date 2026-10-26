import "@/test/mockmap";
import { flushPromises } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import { FakeMap, resetFakes } from "@/test/fakemap";
import { mountStationMap } from "@/test/stationmap";
import { NOW, station, table } from "@/test/fixtures";
import type { StationRow } from "@/protocol/protocol";

type Feature = { geometry: { type: string; coordinates: unknown }; properties: { call: string; previous: number } };
type Mark = StationRow["route_marks"][number];

/** A route as the daemon tells it. */
const rf = (...hops: string[]): Mark => ({ kind: "rf", hops, gate: "", at: "2026-10-21T11:59:00Z", lat: null, lon: null });
const heardBy = (gate: string, ...hops: string[]): Mark => ({ kind: "igate", hops, gate, at: "2026-10-21T11:59:00Z", lat: null, lon: null });

const stations = (extra = {}) =>
  table(
    station("OH2GBA", { is_me: true, lat: 60.17, lon: 24.94, symbol_code: "-" }),
    station("OH2PU-9", { lat: 60.2, lon: 24.65, route_marks: [rf("OH2RCH-1", "OH2RCH-3")], ...extra }),
    station("OH2RCH-1", { lat: 60.3, lon: 24.5, symbol_code: "#" }),
    station("OH2RCH-3", { lat: 60.25, lon: 24.8, symbol_code: "#" }),
    station("OH2RCH-2", { lat: 60.1, lon: 24.7, symbol_code: "#" }),
    station("OH2GW-10", { lat: 60.05, lon: 24.3, symbol_code: "&" }),
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
const drawn = (): Feature[] => (FakeMap.last().getSource("route")?.setData.mock.calls.at(-1)?.[0] as { features: Feature[] }).features;
const lines = () => drawn().filter((f) => f.geometry.type === "LineString");

async function mounted(extra = {}) {
  const { wrapper } = mountStationMap(props(extra));
  await flushPromises();
  FakeMap.last().fire("style.load");
  return wrapper;
}

beforeEach(() => {
  resetFakes();
  localStorage.clear();
});

describe("the route of the selected station", () => {
  it("has layers of its own in the map's style", async () => {
    await mounted();
    expect(FakeMap.last().layers).toEqual(
      expect.arrayContaining(["tracks-line", "route-casing", "route-previous", "route-latest", "route-hops", "route-names"]),
    );
  });

  it("draws nothing while no station is selected", async () => {
    await mounted();
    expect(drawn()).toEqual([]);
  });

  it("runs from the station through its two digipeaters to us, with the digipeaters named", async () => {
    await mounted({ selected: "OH2PU-9" });
    expect(lines().map((f) => f.geometry.coordinates)).toEqual([
      [
        [24.65, 60.2],
        [24.5, 60.3],
        [24.8, 60.25],
        [24.94, 60.17],
      ],
    ]);
    expect(
      drawn()
        .filter((f) => f.geometry.type === "Point")
        .map((f) => f.properties.call),
    ).toEqual(["OH2RCH-1", "OH2RCH-3"]);
  });

  it("goes straight on past a digipeater with no position", async () => {
    const rows = stations();
    rows.set("OH2RCH-1", station("OH2RCH-1", { lat: null, lon: null }));
    await mounted({ stations: rows, selected: "OH2PU-9" });
    expect(lines().map((f) => f.geometry.coordinates)).toEqual([
      [
        [24.65, 60.2],
        [24.8, 60.25],
        [24.94, 60.17],
      ],
    ]);
  });

  it("is drawn when the station is picked, and cleared when the selection is", async () => {
    const wrapper = await mounted();
    await wrapper.setProps({ selected: "OH2PU-9" });
    expect(lines()).toHaveLength(1);
    await wrapper.setProps({ selected: null });
    expect(drawn()).toEqual([]);
  });

  it("follows the station when it is heard by another route", async () => {
    const wrapper = await mounted({ selected: "OH2PU-9" });
    await wrapper.setProps({ stations: stations({ route_marks: [rf()] }) });
    expect(drawn()).toEqual([]);
  });

  it("draws the route before the latest one too, marked, when the packet before it came another way", async () => {
    await mounted({ stations: stations({ route_marks: [rf("OH2RCH-1", "OH2RCH-3"), rf("OH2RCH-2")] }), selected: "OH2PU-9" });
    expect(lines().map((f) => f.properties.previous)).toEqual([0, 1]);
    expect(lines()[1]?.geometry.coordinates).toEqual([
      [24.65, 60.2],
      [24.7, 60.1],
      [24.94, 60.17],
    ]);
  });

  it("ends the route of a packet an iGate heard at the iGate, named with the internet mark", async () => {
    await mounted({ stations: stations({ route_marks: [heardBy("OH2GW-10", "OH2RCH-2")] }), selected: "OH2PU-9" });
    expect(lines().map((f) => f.geometry.coordinates)).toEqual([
      [
        [24.65, 60.2],
        [24.7, 60.1],
        [24.3, 60.05],
      ],
    ]);
    expect(
      drawn()
        .filter((f) => f.geometry.type === "Point")
        .map((f) => (f.properties as unknown as { label: string }).label),
    ).toEqual(["OH2RCH-2", "OH2GW-10 → internet"]);
  });

  it("is drawn again when the style is set again, in the colours of the scheme", async () => {
    const wrapper = await mounted({ selected: "OH2PU-9" });
    await wrapper.setProps({ dark: true });
    FakeMap.last().sources.clear();
    FakeMap.last().fire("style.load");
    expect(lines()).toHaveLength(1);
  });

  it("draws nothing before we have a place", async () => {
    await mounted({ home: null, selected: "OH2PU-9" });
    expect(drawn()).toEqual([]);
  });
});
