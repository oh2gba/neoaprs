import "@/test/mockmap";
import { flushPromises } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import { FakeMap, resetFakes } from "@/test/fakemap";
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

describe("the range circles of the digipeaters", () => {
  it("have layers of their own, over the ALOHA circle and under the tracks and the route", async () => {
    await mounted();
    const layers = FakeMap.last().layers;
    expect(layers).toEqual(expect.arrayContaining(["digipeater-ranges-fill", "digipeater-ranges-line"]));
    expect(layers.indexOf("aloha-line")).toBeLessThan(layers.indexOf("digipeater-ranges-line"));
    expect(layers.indexOf("digipeater-ranges-line")).toBeLessThan(layers.indexOf("tracks-line"));
    expect(layers.indexOf("digipeater-ranges-line")).toBeLessThan(layers.indexOf("route-casing"));
  });

  it("are not drawn while Show range is off", async () => {
    const { wrapper } = await mounted();
    expect(FakeMap.last().sources.has("digipeater-ranges")).toBe(true);
    expect(drawn()).toBeUndefined();
    await wrapper.setProps({ ranges: false });
    expect(drawn()).toBeUndefined();
  });

  it("are drawn for the digipeaters that gave a range when it is turned on, and gone when it is turned off again", async () => {
    const { wrapper } = await mounted();
    await wrapper.setProps({ ranges: true });
    expect(drawn()?.features.map((f) => [f.properties.call, f.properties.km])).toEqual([["OH2RCH-2", 21.4]]);
    expect(drawn()?.features[0]?.geometry.coordinates[0]?.length).toBeGreaterThan(60);
    await wrapper.setProps({ ranges: false });
    expect(drawn()?.features).toEqual([]);
  });

  it("are drawn from the start when Show range was on before the map was", async () => {
    mountStationMap(props({ ranges: true }));
    await flushPromises();
    FakeMap.last().fire("style.load");
    expect((FakeMap.last().getSource("digipeater-ranges")?.data as Rings).features.map((f) => f.properties.call)).toEqual(["OH2RCH-2"]);
  });

  it("follow the digipeaters as they are heard: a new range, a new digipeater", async () => {
    const { wrapper, daemon } = await mounted({ ranges: true });
    await tell(daemon, { stations: stations({ extensions: phg(30) }) });
    expect(drawn()?.features[0]?.properties.km).toBe(30);
    await tell(daemon, { stations: stations({ extensions: null }) });
    expect(drawn()?.features).toEqual([]);
    expect(wrapper.exists()).toBe(true);
  });

  it("are not drawn for a digipeater that is past its timeout and off the map", async () => {
    await mounted({ ranges: true, stations: stations({ last_position_at: ago(5 * 3600), last_heard: ago(5 * 3600) }) });
    expect(drawn()?.features ?? []).toEqual([]);
  });
});
