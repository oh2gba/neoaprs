import "@/test/mockmap";
import { flushPromises } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import { FakeMap, FakeMarker, resetFakes } from "@/test/fakemap";
import { mountStationMap } from "@/test/stationmap";
import { tell } from "@/test/context";
import { NOW, ago, station, table } from "@/test/fixtures";
import type { ExtensionValues } from "@/protocol/protocol";

type Rings = { features: { properties: { call: string; km: number }; geometry: { coordinates: number[][][] } }[] };

const phg = (range_km: number): ExtensionValues => ({
  phg: { power_w: 25, height_m: 12.2, gain_db: 5, direction_deg: null, range_km },
  range_km: null,
  dfs: null,
  df_bearing: null,
  area: null,
});
const stations = (extra = {}) =>
  table(
    station("OH2GBA", { is_me: true, lat: 60.17, lon: 24.94, symbol_code: "-", heard_via: [] }),
    station("OH2RCH-2", { symbol_code: "#", lat: 60.3, lon: 25, heard_via: [], extensions: phg(21.4), ...extra }),
    station("OH2RCH-3", { symbol_code: "#", lat: 60.4, lon: 25.1, heard_via: [] }),
    station("OH2RCH-4", {
      symbol_code: "#",
      lat: 60.9,
      lon: 26.1,
      heard_via: [],
      extensions: { phg: null, range_km: 12, dfs: null, df_bearing: null, area: null },
    }),
    station("OH2CAR", { lat: 60.2, lon: 24.9, heard_via: [["OH2RCH-2", 5]], extensions: phg(99) }),
  );
const props = (extra = {}) => ({
  stations: stations(),
  selected: null,
  focus: null,
  home: { lat: 60.17, lon: 24.94 },
  now: NOW,
  dark: false,
  aging: { defaultMin: 180 },
  ...extra,
});
const drawn = () => FakeMap.last().getSource("digipeater-ranges")?.setData.mock.calls.at(-1)?.[0] as Rings | undefined;

async function mounted(extra = {}) {
  const { wrapper, daemon } = mountStationMap(props(extra));
  await flushPromises();
  FakeMap.last().fire("style.load");
  return { wrapper, daemon };
}

beforeEach(() => {
  resetFakes();
  localStorage.clear();
});

const click = (call: string) =>
  FakeMarker.live()
    .find((m) => m.element.textContent === call)
    ?.element.click();

describe("the range circle of the selected digipeater", () => {
  it("has layers of its own, over the ALOHA circle and under the tracks and the route", async () => {
    await mounted();
    const layers = FakeMap.last().layers;
    expect(layers).toEqual(expect.arrayContaining(["digipeater-ranges-fill", "digipeater-ranges-line"]));
    expect(layers.indexOf("aloha-line")).toBeLessThan(layers.indexOf("digipeater-ranges-line"));
    expect(layers.indexOf("digipeater-ranges-line")).toBeLessThan(layers.indexOf("tracks-line"));
    expect(layers.indexOf("digipeater-ranges-line")).toBeLessThan(layers.indexOf("route-casing"));
  });

  it("is not drawn without a selection, whatever digipeaters there are", async () => {
    await mounted();
    expect(FakeMap.last().sources.has("digipeater-ranges")).toBe(true);
    expect((FakeMap.last().getSource("digipeater-ranges")?.data as Rings).features).toEqual([]);
    expect(drawn()).toBeUndefined();
  });

  it("is drawn for the selected digipeater that gave a range, one circle only, and is gone with the selection", async () => {
    const { wrapper } = await mounted();
    await wrapper.setProps({ selected: "OH2RCH-2" });
    expect(drawn()?.features.map((f) => [f.properties.call, f.properties.km])).toEqual([["OH2RCH-2", 21.4]]);
    expect(drawn()?.features[0]?.geometry.coordinates[0]?.length).toBeGreaterThan(60);
    await wrapper.setProps({ selected: "OH2RCH-4" });
    expect(drawn()?.features.map((f) => [f.properties.call, f.properties.km])).toEqual([["OH2RCH-4", 12]]); // (the PHG one is not kept)
    await wrapper.setProps({ selected: null });
    expect(drawn()?.features).toEqual([]);
  });

  it("is only the selected one's: the other open cards have none", async () => {
    const { wrapper } = await mounted();
    await wrapper.setProps({ selected: "OH2RCH-2", others: ["OH2RCH-4"] });
    expect(drawn()?.features.map((f) => f.properties.call)).toEqual(["OH2RCH-2"]);
  });

  it("is none for a selected digipeater with no range, and none for a station that is not a digipeater", async () => {
    const { wrapper } = await mounted();
    await wrapper.setProps({ selected: "OH2RCH-3" });
    expect(drawn()?.features ?? []).toEqual([]);
    await wrapper.setProps({ selected: "OH2CAR" }); // (it gave a range, but nobody heard it repeat)
    expect(drawn()?.features ?? []).toEqual([]);
    await wrapper.setProps({ selected: "OH2GBA" });
    expect(drawn()?.features ?? []).toEqual([]);
  });

  it("is drawn from the start when the station was selected before the map was", async () => {
    mountStationMap(props({ selected: "OH2RCH-2" }));
    await flushPromises();
    FakeMap.last().fire("style.load");
    expect((FakeMap.last().getSource("digipeater-ranges")?.data as Rings).features.map((f) => f.properties.call)).toEqual(["OH2RCH-2"]);
  });

  it("follows the row of the selected station: a new range, no range, a new position", async () => {
    const { wrapper, daemon } = await mounted({ selected: "OH2RCH-2" });
    await tell(daemon, { stations: stations({ extensions: phg(30) }) });
    expect(drawn()?.features[0]?.properties.km).toBe(30);
    await tell(daemon, { stations: stations({ lat: 60.5 }) });
    expect(drawn()?.features[0]?.geometry.coordinates[0]?.[0]?.[1]).toBeGreaterThan(60.5);
    await tell(daemon, { stations: stations({ extensions: null }) });
    expect(drawn()?.features).toEqual([]);
    expect(wrapper.exists()).toBe(true);
  });

  it("is drawn for a selected digipeater past its timeout, as its marker is", async () => {
    await mounted({ selected: "OH2RCH-2", stations: stations({ last_position_at: ago(5 * 3600), last_heard: ago(5 * 3600) }) });
    expect((FakeMap.last().getSource("digipeater-ranges")?.data as Rings).features.map((f) => f.properties.call)).toEqual(["OH2RCH-2"]);
  });
});

describe("the map and the range circle of a station that is picked", () => {
  const box = (fit: { bounds: [[number, number], [number, number]] } | undefined) => {
    const ring = drawn()?.features[0]?.geometry.coordinates[0] ?? [];
    const lons = ring.map((p) => p[0] ?? 0);
    const lats = ring.map((p) => p[1] ?? 0);
    return {
      drawn: [
        [Math.min(...lons), Math.min(...lats)],
        [Math.max(...lons), Math.max(...lats)],
      ],
      fit: fit?.bounds,
    };
  };

  it("fits itself to the whole circle when a digipeater with a range is picked in a table, and does not fly to the point", async () => {
    const { wrapper } = await mounted();
    await wrapper.setProps({ selected: "OH2RCH-2", focus: { call: "OH2RCH-2", n: 1 } });
    await flushPromises();
    const map = FakeMap.last();
    expect(map.flights).toEqual([]);
    expect(map.fits).toHaveLength(1);
    const { drawn: ring, fit } = box(map.fits[0]);
    expect(fit).toEqual(ring);
    expect(fit?.[0]?.[0]).toBeLessThan(25); // (21.4 km round 25.0 E)
    expect(map.fits[0]?.options).toEqual({ padding: { left: 40, right: 40, top: 40, bottom: 40 } });
  });

  it("fits again when the same digipeater is picked again, and to the next one's circle when another is", async () => {
    const { wrapper } = await mounted();
    await wrapper.setProps({ selected: "OH2RCH-2", focus: { call: "OH2RCH-2", n: 1 } });
    await wrapper.setProps({ focus: { call: "OH2RCH-2", n: 2 } });
    await wrapper.setProps({ selected: "OH2RCH-4", focus: { call: "OH2RCH-4", n: 3 } });
    await flushPromises();
    expect(FakeMap.last().fits).toHaveLength(3);
    expect(FakeMap.last().flights).toEqual([]);
    expect(FakeMap.last().fits[2]?.bounds[0][0]).toBeGreaterThan(25.5);
  });

  it("fits itself to the circle when the marker of the selected digipeater is clicked, and leaves a plain station's marker alone", async () => {
    // (the page makes the clicked marker the selected station in the same tick; here the selection is told first)
    const { wrapper } = await mounted({ selected: "OH2RCH-2" });
    click("OH2RCH-2");
    await flushPromises();
    expect(FakeMap.last().fits).toHaveLength(1);
    expect(FakeMap.last().flights).toEqual([]);
    click("OH2RCH-2"); // (picked again: the map is brought back to the circle)
    await flushPromises();
    expect(FakeMap.last().fits).toHaveLength(2);
    await wrapper.setProps({ selected: "OH2CAR" });
    click("OH2CAR");
    await flushPromises();
    await wrapper.setProps({ selected: "OH2RCH-3" }); // (a digipeater with no range)
    click("OH2RCH-3");
    await flushPromises();
    expect(FakeMap.last().fits).toHaveLength(2);
    expect(FakeMap.last().flights).toEqual([]);
  });

  it("does not fit for a click on a marker that did not become the selected station (a Ctrl+click that closed its card)", async () => {
    await mounted({ selected: "OH2CAR" });
    click("OH2RCH-2");
    await flushPromises();
    expect(FakeMap.last().fits).toEqual([]);
  });

  it("flies to a station that has no circle, a plain one or a digipeater with no range, as it did", async () => {
    const { wrapper } = await mounted();
    await wrapper.setProps({ selected: "OH2CAR", focus: { call: "OH2CAR", n: 1 } });
    await wrapper.setProps({ selected: "OH2RCH-3", focus: { call: "OH2RCH-3", n: 2 } });
    await flushPromises();
    expect(FakeMap.last().flights).toEqual([
      { center: [24.9, 60.2], zoom: 11 },
      { center: [25.1, 60.4], zoom: 11 },
    ]);
    expect(FakeMap.last().fits).toEqual([]);
  });

  it("moves nothing when the selection is let go of, or when a digipeater is selected without being picked", async () => {
    const { wrapper } = await mounted({ selected: "OH2RCH-2" });
    expect(FakeMap.last().fits).toEqual([]); // (a card that came back with the page)
    await wrapper.setProps({ selected: null });
    await flushPromises();
    expect([FakeMap.last().fits, FakeMap.last().flights, FakeMap.last().jumps, FakeMap.last().pans]).toEqual([[], [], [], []]);
  });
});
