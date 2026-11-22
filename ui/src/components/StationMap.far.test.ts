import "@/test/mockmap";
import { flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import StationsTable from "@/components/StationsTable.vue";
import { mount } from "@vue/test-utils";
import { FakeMarker, resetFakes } from "@/test/fakemap";
import { fakeDaemon, withDaemon } from "@/test/context";
import { mountStationMap } from "@/test/stationmap";
import { NOW, ago, configValues, station, table } from "@/test/fixtures";

// A station heard on a radio is shown wherever it is: the map's Radius sets the download and the
// Internet stations, never what a radio hears.
const stations = () =>
  table(
    station("OH2GBA", { is_me: true, lat: 60.17, lon: 24.94, distance_km: null, symbol_code: "-" }),
    station("OH2NEAR", { lat: 60.2, lon: 24.9, distance_km: 4, last_heard: ago(30), last_position_at: ago(30) }),
    station("VK2FM", { lat: -33.87, lon: 151.21, distance_km: 15_100, last_heard: ago(60), last_position_at: ago(60) }),
    station("W6HF", { lat: 37.77, lon: -122.42, distance_km: 8_800, last_heard: ago(90), last_position_at: ago(90) }),
  );

beforeEach(() => {
  resetFakes();
  localStorage.clear();
});
afterEach(() => document.body.replaceChildren());

describe("stations far outside the map's radius", () => {
  it("are drawn on the map as the near ones are", async () => {
    mountStationMap({ stations: stations(), selected: null, focus: null, home: { lat: 60.17, lon: 24.94 }, now: NOW, dark: false, aging: { defaultMin: 0 } });
    await flushPromises();
    const drawn = FakeMarker.live().map((m) => m.element.textContent);
    expect(drawn).toEqual(expect.arrayContaining(["OH2NEAR", "VK2FM", "W6HF"]));
  });

  it("are in the table of stations", () => {
    const wrapper = mount(StationsTable, {
      props: { selected: null },
      global: withDaemon(fakeDaemon({ config: configValues({ "map/radius_km": "10" }), stations: stations(), aging: { defaultMin: 0 } })),
    });
    const calls = wrapper.findAll("tbody tr td.call .callname").map((td) => td.text());
    expect(calls).toEqual(expect.arrayContaining(["OH2NEAR", "VK2FM", "W6HF"]));
  });
});
