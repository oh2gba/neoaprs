import "@/test/mockmap";
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { defineComponent, h, ref } from "vue";
import StationMap from "@/components/StationMap.vue";
import type { Aging } from "@/lib/aging";
import { writeView } from "@/lib/mapview";
import { OPEN_ZOOM } from "@/lib/basemapstyle";
import { FakeMap, FakeMarker, fakeState, resetFakes } from "@/test/fakemap";
import { fakeDaemon, withDaemon } from "@/test/context";
import { mountStationMap } from "@/test/stationmap";
import { NOW, ago, station, table } from "@/test/fixtures";

const stations = () =>
  table(
    station("OH2GBA", { is_me: true, lat: 60.17, lon: 24.94, symbol_code: "-" }),
    station("OH2PU-9", {
      lat: 60.2,
      lon: 24.65,
      last_position_at: ago(100),
      track: [
        [ago(300), 60.19, 24.6],
        [ago(100), 60.2, 24.65],
      ],
    }),
    station("OH2OLD", { lat: 60.3, lon: 25.1, last_position_at: ago(2 * 3600) }),
    station("OH2ANCIENT", { lat: 60.4, lon: 25.2, last_position_at: ago(3 * 86400) }),
    station("OH2NOPOS", { lat: null, lon: null }),
  );

const aging = (defaultMin: number): Aging => ({ defaultMin });
const props = (extra = {}) => ({
  stations: stations(),
  selected: null,
  focus: null,
  home: { lat: 60.17, lon: 24.94 },
  now: NOW,
  dark: false,
  aging: aging(0),
  ...extra,
});
const markerOf = (call: string) => FakeMarker.live().find((m) => m.element.textContent === call);
const lastData = () => FakeMap.last().getSource("tracks")?.setData.mock.calls.at(-1)?.[0] as { features: { properties: { call: string; opacity: number } }[] };

async function mounted(extra = {}) {
  const { wrapper } = mountStationMap(props(extra));
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  resetFakes();
  localStorage.clear();
});
afterEach(() => document.body.replaceChildren());

describe("StationMap", () => {
  it("opens on our own station at zoom 9, in the base map's style", async () => {
    await mounted();
    const map = FakeMap.last();
    expect(map.options.center).toEqual([24.94, 60.17]);
    expect(map.options.zoom).toBe(OPEN_ZOOM);
    expect(JSON.stringify(map.options.style)).toContain("pmtiles://");
  });

  it("opens on the world while we have no position", async () => {
    await mounted({ home: null });
    expect(FakeMap.last().options.center).toEqual([0, 20]);
    expect(FakeMap.last().options.zoom).toBe(1.5);
  });

  it("opens where it was left", async () => {
    writeView({ lat: 61, lon: 25, zoom: 11 });
    await mounted();
    expect(FakeMap.last().options.center).toEqual([25, 61]);
    expect(FakeMap.last().options.zoom).toBe(11);
  });

  describe("an object or an item of ours", () => {
    const withOurs = () =>
      table(
        station("OH2GBA", { is_me: true, lat: 60.17, lon: 24.94, symbol_code: "-" }),
        station("OH2PU-9", { lat: 60.2, lon: 24.65 }),
        station("LEADER", { kind: "object", own: true, reported_by: "OH2GBA", lat: 60.3, lon: 25.0, last_position_at: ago(5 * 86400) }),
      );

    it("has a marker that can be dragged, marked as ours, and no other marker can", async () => {
      await mounted({ stations: withOurs() });
      expect(markerOf("LEADER")?.draggable).toBe(true);
      expect(markerOf("LEADER")?.element.classList.contains("stn--own")).toBe(true);
      expect(markerOf("OH2PU-9")?.draggable).toBe(false);
      expect(markerOf("OH2GBA")?.draggable).toBe(false);
    });

    it("is never past its timeout, however old", async () => {
      await mounted({ stations: withOurs(), aging: aging(60) });
      expect(markerOf("LEADER")).toBeDefined();
    });

    it("says where it was dropped", async () => {
      const wrapper = await mounted({ stations: withOurs() });
      markerOf("LEADER")?.dragTo(60.5, 25.5);
      expect(wrapper.emitted("move")).toEqual([["LEADER", 60.5, 25.5]]);
    });

    it("stops being draggable when it is no longer ours (another station took the name)", async () => {
      const wrapper = await mounted({ stations: withOurs() });
      const taken = withOurs();
      taken.set("LEADER", station("LEADER", { kind: "object", own: false, reported_by: "OH2XYZ", lat: 60.3, lon: 25.0 }));
      await wrapper.setProps({ stations: taken });
      expect(markerOf("LEADER")?.draggable).toBe(false);
    });
  });

  it("puts a marker with the call on every station that has a position, and none on the rest", async () => {
    await mounted();
    const calls = FakeMarker.live().map((m) => m.element.querySelector(".stn-label")?.textContent);
    expect(calls.sort()).toEqual(["OH2ANCIENT", "OH2GBA", "OH2OLD", "OH2PU-9"]);
    const marker = FakeMarker.live().find((m) => m.element.textContent === "OH2PU-9");
    expect(marker?.lngLat).toEqual([24.65, 60.2]);
  });

  it("tells our own station, and dims the others in steps on the way to their timeout", async () => {
    await mounted({ aging: aging(240) });
    const of = (call: string) => markerOf(call)?.element;
    expect(of("OH2GBA")?.classList.contains("stn--me")).toBe(true);
    expect([...(of("OH2PU-9")?.classList ?? [])].some((c) => c.startsWith("stn--fade"))).toBe(false);
    expect(of("OH2OLD")?.classList.contains("stn--fade-2")).toBe(true); // 2 h of 4 h
  });

  it("puts a ring on a station heard direct within the last hour, and takes it off when the hour has passed", async () => {
    const rows = table(
      station("OH2NEAR", { last_direct_at: ago(300) }),
      station("OH2ONCE", { last_direct_at: ago(2 * 3600) }),
      station("OH2FAR", { last_direct_at: null }),
    );
    const wrapper = await mounted({ stations: rows });
    const ringed = (call: string) => markerOf(call)?.element.classList.contains("stn--direct");
    expect([ringed("OH2NEAR"), ringed("OH2ONCE"), ringed("OH2FAR")]).toEqual([true, false, false]);
    await wrapper.setProps({ now: NOW + 3600_000 });
    expect(ringed("OH2NEAR")).toBe(false);
  });

  it("dims a marker more as time goes, and never our own", async () => {
    const wrapper = await mounted({ aging: aging(240) });
    await wrapper.setProps({ now: NOW + 3600_000 });
    expect(markerOf("OH2OLD")?.element.classList.contains("stn--fade-3")).toBe(true);
    expect(markerOf("OH2GBA")?.element.classList.contains("stn--fade-3")).toBe(false);
  });

  it("does not draw a station past its timeout, neither its marker nor its track, until it is selected", async () => {
    const wrapper = await mounted({ aging: aging(1) });
    FakeMap.last().fire("style.load");
    expect(markerOf("OH2OLD")).toBeUndefined();
    expect(markerOf("OH2PU-9")).toBeUndefined(); // last position 100 s ago, timeout 1 min
    expect(markerOf("OH2ANCIENT")).toBeUndefined();
    expect(markerOf("OH2GBA")).toBeDefined();
    expect(lastData().features).toHaveLength(0);
    await wrapper.setProps({ selected: "OH2OLD" });
    expect(markerOf("OH2OLD")?.element.classList.contains("stn--selected")).toBe(true);
    await wrapper.setProps({ selected: null });
    expect(markerOf("OH2OLD")).toBeUndefined();
  });

  it("hides a station past the timeout, and a change of the timeout is drawn at once", async () => {
    const wrapper = await mounted({ aging: aging(60) });
    expect(markerOf("OH2OLD")).toBeUndefined();
    expect(markerOf("OH2ANCIENT")).toBeUndefined();
    expect(markerOf("OH2PU-9")).toBeDefined();
    await wrapper.setProps({ aging: aging(0) });
    expect(markerOf("OH2OLD")).toBeDefined();
  });

  it("moves a marker when the station moves, and removes it when the station is gone", async () => {
    const rows = stations();
    const wrapper = await mounted({ stations: rows });
    const next = new Map(rows);
    next.set("OH2PU-9", station("OH2PU-9", { lat: 60.5, lon: 24.7 }));
    next.delete("OH2OLD");
    await wrapper.setProps({ stations: next });
    expect(FakeMarker.live().find((m) => m.element.textContent === "OH2PU-9")?.lngLat).toEqual([24.7, 60.5]);
    expect(FakeMarker.live().some((m) => m.element.textContent === "OH2OLD")).toBe(false);
  });

  it("draws the tracks of the stations that have more than one track point, each stretch with its opacity", async () => {
    await mounted({ aging: aging(10) });
    const map = FakeMap.last();
    map.fire("style.load");
    expect(map.layers).toContain("tracks-line");
    expect(lastData().features.map((f) => f.properties.call)).toEqual(["OH2PU-9"]);
    expect(lastData().features[0]?.properties.opacity).toBeLessThan(1);
  });

  it("draws the selected station's trail above the others, with a dot at each of its positions, and no dots for no selection", async () => {
    const wrapper = await mounted({ aging: aging(10) });
    const map = FakeMap.last();
    map.fire("style.load");
    expect(map.layers.slice(map.layers.indexOf("tracks-line"))).toEqual(
      expect.arrayContaining(["tracks-line", "tracks-selected-casing", "tracks-selected", "tracks-points"]),
    );
    expect(map.layers.indexOf("tracks-selected")).toBeGreaterThan(map.layers.indexOf("tracks-line"));
    expect(map.layers.indexOf("tracks-points")).toBeGreaterThan(map.layers.indexOf("tracks-selected"));
    const points = () =>
      (
        map.getSource("track-points")?.setData.mock.calls.at(-1)?.[0] as {
          features: { properties: { call: string; opacity: number }; geometry: { coordinates: [number, number] } }[];
        }
      ).features;
    expect(points()).toEqual([]);
    await wrapper.setProps({ selected: "OH2PU-9" });
    expect(points().map((f) => f.geometry.coordinates)).toEqual([
      [24.6, 60.19],
      [24.65, 60.2],
    ]);
    expect(points().map((f) => f.properties.call)).toEqual(["OH2PU-9", "OH2PU-9"]);
    expect(lastData().features.find((f) => f.properties.call === "OH2PU-9")).toMatchObject({ properties: { selected: 1 } });
  });

  it("draws the tracks again once a minute and when a station changes, not at every tick of the clock", async () => {
    const wrapper = await mounted({ aging: aging(10) });
    FakeMap.last().fire("style.load");
    const calls = () => FakeMap.last().getSource("tracks")?.setData.mock.calls.length ?? 0;
    const before = calls();
    await wrapper.setProps({ now: NOW + 5000 });
    expect(calls()).toBe(before);
    await wrapper.setProps({ now: NOW + 65_000 });
    expect(calls()).toBe(before + 1);
    await wrapper.setProps({ stations: stations() });
    expect(calls()).toBe(before + 2);
  });

  it("says which station a click on its marker selects, and lets go of it on a click on the map", async () => {
    const wrapper = await mounted();
    FakeMarker.live()
      .find((m) => m.element.textContent === "OH2PU-9")
      ?.element.click();
    FakeMap.last().fire("click");
    expect(wrapper.emitted("select")).toEqual([["OH2PU-9", false], [null]]);
  });

  it("marks the selected station", async () => {
    const wrapper = await mounted();
    await wrapper.setProps({ selected: "OH2PU-9" });
    expect(
      FakeMarker.live()
        .find((m) => m.element.textContent === "OH2PU-9")
        ?.element.classList.contains("stn--selected"),
    ).toBe(true);
  });

  it("flies to a station it is asked to, not closer than zoom 11", async () => {
    const wrapper = await mounted();
    await wrapper.setProps({ focus: { call: "OH2PU-9", n: 1 } });
    expect(FakeMap.last().flights).toEqual([{ center: [24.65, 60.2], zoom: 11 }]);
    FakeMap.last().zoom = 13;
    await wrapper.setProps({ focus: { call: "OH2PU-9", n: 2 } });
    expect(FakeMap.last().flights[1]).toEqual({ center: [24.65, 60.2], zoom: 13 });
    await wrapper.setProps({ focus: { call: "OH2NOPOS", n: 3 } });
    expect(FakeMap.last().flights).toHaveLength(2);
  });

  it("remembers where it was left", async () => {
    await mounted();
    FakeMap.last().center = { lng: 25.5, lat: 60.9 };
    FakeMap.last().zoom = 10;
    FakeMap.last().fire("moveend");
    expect(JSON.parse(localStorage.getItem("NeoAPRS.mapview") ?? "{}")).toEqual({ lat: 60.9, lon: 25.5, zoom: 10 });
  });

  it("changes the style with the colour scheme", async () => {
    const wrapper = await mounted();
    await wrapper.setProps({ dark: true });
    expect(FakeMap.last().styles).toHaveLength(2);
  });

  it("has no base map: says so over a blank background, offers the download, and draws the stations all the same", async () => {
    fakeState.archive = false;
    const wrapper = await mounted();
    expect(wrapper.find(".mapnote span").text()).toBe("No base map");
    expect(JSON.stringify(FakeMap.last().options.style)).not.toContain("pmtiles");
    expect(FakeMarker.live().length).toBe(4);
    expect(wrapper.text()).not.toContain("fetch-basemap");
    await wrapper.find(".mapnote button").trigger("click");
    expect(wrapper.emitted("download")).toHaveLength(1);
  });

  it("has only the world: draws it, and still offers the detailed map", async () => {
    fakeState.archive = false;
    fakeState.world = true;
    const wrapper = await mounted();
    expect(wrapper.find(".mapnote span").text()).toBe("No detailed map");
    expect(wrapper.find(".mapnote button").exists()).toBe(true);
    const style = JSON.stringify(FakeMap.last().options.style);
    expect(style).toContain("basemap-world.pmtiles");
    expect(style).not.toContain("pmtiles://http://127.0.0.1:7303/basemap.pmtiles");
  });

  it("has both files: draws the world under the detailed map and has no note", async () => {
    fakeState.world = true;
    const wrapper = await mounted();
    expect(wrapper.find(".mapnote").exists()).toBe(false);
    const style = FakeMap.last().options.style as { sources: Record<string, unknown>; layers: { id: string }[] };
    expect(Object.keys(style.sources).sort()).toEqual(["base", "world"]);
    const ids = style.layers.map((l) => l.id);
    expect(ids.indexOf("world-earth")).toBeLessThan(ids.indexOf("earth"));
  });

  it("reads the files again when the daemon makes them: the style is set once more, the addresses new", async () => {
    fakeState.archive = false;
    const wrapper = await mounted({ filesKey: "- -" });
    expect(wrapper.find(".mapnote span").text()).toBe("No base map");
    fakeState.archive = true;
    fakeState.world = true;
    await wrapper.setProps({ filesKey: "2026-10-22T19:03:53Z 2026-10-22T19:00:00Z" });
    await flushPromises();
    expect(wrapper.find(".mapnote").exists()).toBe(false);
    const styles = FakeMap.last().styles;
    expect(styles).toHaveLength(2);
    expect(JSON.stringify(styles[1])).toContain("basemap.pmtiles?v=1");
    expect(JSON.stringify(styles[1])).toContain("basemap-world.pmtiles?v=1");
    fakeState.archive = true;
    await wrapper.setProps({ filesKey: "2026-10-23T08:00:00Z 2026-10-22T19:00:00Z" });
    await flushPromises();
    expect(JSON.stringify(FakeMap.last().styles[2])).toContain("basemap.pmtiles?v=2");
  });

  it("does not set the style again for the first word of the daemon, or for a key that did not change", async () => {
    const wrapper = await mounted();
    await wrapper.setProps({ filesKey: "2026-10-22T19:03:53Z -" });
    await flushPromises();
    await wrapper.setProps({ filesKey: "2026-10-22T19:03:53Z -" });
    await flushPromises();
    expect(FakeMap.last().styles).toHaveLength(1);
  });

  it("shows a crosshair while it waits for the click of a place", async () => {
    const wrapper = await mounted();
    expect(wrapper.find(".mapbox").classes()).not.toContain("map-picking");
    await wrapper.setProps({ picking: true });
    expect(wrapper.find(".mapbox").classes()).toContain("map-picking");
  });

  it("lets the pin of the guide be dragged, and gives where it was dropped as the place", async () => {
    const wrapper = await mounted({ pin: { lat: 60.1, lon: 24.9 }, picking: true });
    const pin = FakeMarker.live().find((m) => m.element.classList.contains("setuppin"));
    expect(pin?.draggable).toBe(true);
    pin?.dragTo(60.4295, 24.1452);
    expect(wrapper.emitted("pick")?.at(-1)).toEqual([{ lat: 60.4295, lon: 24.1452 }]);
  });

  it("gives a click on the map as a place only while the first-run guide is picking, and still lets go of the selection", async () => {
    const wrapper = await mounted();
    FakeMap.last().fire("click", { lngLat: { lat: 60.1, lng: 24.9 } });
    expect(wrapper.emitted("pick")).toBeUndefined();
    expect(wrapper.emitted("select")).toEqual([[null]]);
    await wrapper.setProps({ picking: true });
    FakeMap.last().fire("click", { lngLat: { lat: 60.1, lng: 24.9 } });
    expect(wrapper.emitted("pick")).toEqual([[{ lat: 60.1, lon: 24.9 }]]);
    FakeMap.last().fire("click"); // (a click without a place, as the other tests fire it)
    expect(wrapper.emitted("pick")).toHaveLength(1);
  });

  it("shows the place the guide holds with a marker of its own, moves it, and takes it away", async () => {
    const wrapper = await mounted({ pin: { lat: 60.1, lon: 24.9 } });
    const pins = () => FakeMarker.live().filter((m) => m.element.classList.contains("setuppin"));
    expect(pins()).toHaveLength(1);
    expect(pins()[0]?.lngLat).toEqual([24.9, 60.1]);
    expect(FakeMap.last().flights).toEqual([]); // it was there when the map opened
    await wrapper.setProps({ pin: { lat: 61, lon: 25 } });
    expect(pins()).toHaveLength(1);
    expect(pins()[0]?.lngLat).toEqual([25, 61]);
    expect(FakeMap.last().flights).toEqual([{ center: [25, 61], zoom: 9 }]); // typed: the map goes there
    await wrapper.setProps({ pin: null });
    expect(pins()).toHaveLength(0);
    await wrapper.setProps({ pin: { lat: 62, lon: 26 } });
    expect(pins()).toHaveLength(1);
    wrapper.unmount();
    expect(pins()).toHaveLength(0);
  });

  it("does not fly to a place that was clicked, and flies to the next one that is typed", async () => {
    const pin = ref<{ lat: number; lon: number } | null>(null);
    const { stations, home, now, dark, aging, ...own } = props({ picking: true });
    const wrapper = mount(
      defineComponent({
        render: () => h(StationMap, { ...own, pin: pin.value, onPick: (at: { lat: number; lon: number }) => (pin.value = at) }),
      }),
      { global: withDaemon(fakeDaemon({ stations, home, now, dark, aging })), attachTo: document.body },
    );
    await flushPromises();
    FakeMap.last().fire("click", { lngLat: { lat: 60.1, lng: 24.9 } });
    await flushPromises();
    expect(pin.value).toEqual({ lat: 60.1, lon: 24.9 });
    expect(FakeMarker.live().filter((m) => m.element.classList.contains("setuppin"))).toHaveLength(1);
    expect(FakeMap.last().flights).toEqual([]);
    pin.value = { lat: 59, lon: 23 };
    await flushPromises();
    expect(FakeMap.last().flights).toEqual([{ center: [23, 59], zoom: 9 }]);
    wrapper.unmount();
  });

  it("says so when the map cannot be loaded", async () => {
    fakeState.engine = false;
    const wrapper = await mounted();
    expect(wrapper.find(".mapnote").text()).toBe("The map could not be loaded");
    expect(FakeMap.all).toHaveLength(0);
  });

  it("has the credits behind an (i)", async () => {
    const wrapper = await mounted();
    expect(wrapper.find(".attrib-text").exists()).toBe(false);
    await wrapper.find(".attrib-toggle").trigger("click");
    expect(wrapper.find(".attrib-text").text()).toContain("OpenStreetMap");
    expect(wrapper.find(".attrib-text").text()).toContain("OH7LZB");
  });

  it("takes the map away when it goes", async () => {
    const wrapper = await mounted();
    wrapper.unmount();
    expect(FakeMap.last().removed).toBe(true);
    expect(FakeMarker.live()).toHaveLength(0);
  });
});
