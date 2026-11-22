import "@/test/mockmap";
import { flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { nextTick } from "vue";
import { forgetLayerTicks } from "@/composables/useMapLayers";
import { positionToLocator } from "@/lib/locator";
import { FakeMap, resetFakes } from "@/test/fakemap";
import { tell } from "@/test/context";
import { cssRule, mediaRule } from "@/test/css";
import { mountStationMap } from "@/test/stationmap";
import { NOW, ago, mapState, station, table } from "@/test/fixtures";

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
    station("OH2MM-9", {
      lat: 60.3,
      lon: 24.8,
      last_position_at: ago(120),
      track: [
        [ago(400), 60.28, 24.75],
        [ago(120), 60.3, 24.8],
      ],
    }),
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

type Lines = { features: { properties: { call: string } }[] };
type Grid = { features: { properties: { name?: string; rank?: number }; geometry: { type: string } }[] };
const last = <T>(source: string): T => FakeMap.last().getSource(source)?.setData.mock.calls.at(-1)?.[0] as T;
const trackCalls = () => [...new Set(last<Lines>("tracks").features.map((feature) => feature.properties.call))].sort();
const control = () => FakeMap.last().controls.find((box) => box.classList.contains("layers-ctrl"));
const tick = (id: string) => control()?.querySelector<HTMLInputElement>(`.layers-row[data-layer="${id}"] input`);

async function mounted(extra = {}) {
  const made = mountStationMap(props(extra));
  await flushPromises();
  FakeMap.last().fire("style.load");
  return made;
}

async function setTick(id: string, on: boolean): Promise<void> {
  if (!control()?.querySelector(".layers-box")) control()?.querySelector<HTMLButtonElement>(".layers-toggle")?.click();
  await nextTick();
  const box = tick(id);
  if (box && box.checked !== on) box.click();
  await nextTick();
}

beforeEach(() => {
  resetFakes();
  localStorage.clear();
  forgetLayerTicks();
});
afterEach(() => document.body.replaceChildren());

describe("the map's Layers button", () => {
  it("stands among the map's controls in the top left, after the zoom buttons, in their group", async () => {
    await mounted();
    const box = control();
    expect(box?.classList.contains("maplibregl-ctrl-group")).toBe(true);
    expect(box?.querySelector(".layers-toggle")?.getAttribute("aria-label")).toBe("Layers");
  });

  it("moves the replay bar on a phone down under the Layers button, as a finger sizes it", () => {
    expect(cssRule(".size-phone .replaybar")).toMatch(/top:\s*150px/);
  });

  it("is kept clear of by the station cards, whose row begins under it, lower where a finger sizes the buttons", () => {
    expect(cssRule(".cardstack")).toMatch(/--row-top:\s*120px/);
    expect(cssRule(".cardstack")).toMatch(/top:\s*var\(--row-top\)/);
    expect(mediaRule("(pointer: coarse)", ".cardstack")).toMatch(/--row-top:\s*150px/);
  });

  it("lets a card dragged out of the row be as tall as the map, whatever the row's top", () => {
    expect(cssRule(".cardstack .card.moved")).toMatch(/max-height:\s*calc\(100% \+ var\(--row-top\) \+ 30px\)/);
  });

  it("lies above the station cards while its box is open, and under them again once it is closed", () => {
    expect(cssRule(".stationmap:has(.layers-box)")).toMatch(/z-index:\s*auto/);
    expect(cssRule(".stationmap:has(.layers-box) .maplibregl-ctrl-top-left")).toMatch(/z-index:\s*4/);
    expect(cssRule(".cardstack")).toMatch(/z-index:\s*3/);
    expect(cssRule(".stationmap")).toMatch(/z-index:\s*0/);
  });
});

describe("Tracks", () => {
  it("are drawn for every station that moved while the row is ticked, as out of the box", async () => {
    await mounted();
    expect(trackCalls()).toEqual(["OH2MM-9", "OH2PU-9"]);
  });

  it("off, take every track away but the open cards' own, and come back when ticked again", async () => {
    const { wrapper } = await mounted();
    await setTick("tracks", false);
    expect(trackCalls()).toEqual([]);
    await wrapper.setProps({ selected: "OH2PU-9" });
    expect(trackCalls()).toEqual(["OH2PU-9"]);
    await wrapper.setProps({ others: ["OH2MM-9"] });
    expect(trackCalls()).toEqual(["OH2MM-9", "OH2PU-9"]);
    await wrapper.setProps({ selected: null, others: [] });
    expect(trackCalls()).toEqual([]);
    await setTick("tracks", true);
    expect(trackCalls()).toEqual(["OH2MM-9", "OH2PU-9"]);
  });

  it("off, stay off after a reload of the page", async () => {
    await mounted();
    await setTick("tracks", false);
    document.body.replaceChildren();
    forgetLayerTicks();
    await mounted();
    expect(trackCalls()).toEqual([]);
  });
});

describe("the ALOHA circle", () => {
  it("off, goes from the map, and comes back when ticked again", async () => {
    const { daemon } = await mounted();
    await tell(daemon, { map: mapState({ aloha: [{ radio: 1, km: 42 }] }) });
    expect(last<Lines>("aloha").features).toHaveLength(1);
    await setTick("aloha", false);
    expect(last<Lines>("aloha").features).toEqual([]);
    await tell(daemon, { map: mapState({ aloha: [{ radio: 1, km: 50 }] }) });
    expect(last<Lines>("aloha").features).toEqual([]);
    await setTick("aloha", true);
    expect(last<Lines>("aloha").features).toHaveLength(1);
  });

  it("has no title on the map", async () => {
    const { wrapper, daemon } = await mounted();
    await tell(daemon, { map: mapState({ aloha: [{ radio: 1, km: 42 }] }) });
    FakeMap.last().fire("mouseenter", undefined, "aloha-line");
    expect(wrapper.find(".mapbox").attributes("title")).toBeUndefined();
  });
});

describe("the locator grid", () => {
  it("lies under everything else the page draws: the circles, the tracks, the route and the replay", async () => {
    await mounted();
    const layers = FakeMap.last().layers;
    const at = (id: string) => layers.indexOf(id);
    expect(at("grid-lines")).toBe(0);
    expect(at("grid-names")).toBe(1);
    for (const id of ["aloha-halo", "tracks-line", "route-casing", "replay-trails"])
      expect(at(id)).toBeGreaterThan(at("grid-names"));
  });

  it("draws nothing out of the box, and its lines and names when ticked, again when the view stops moving, and nothing when off again", async () => {
    await mounted();
    const map = FakeMap.last();
    expect((map.getSource("grid")?.data as Grid).features).toEqual([]);
    map.zoom = 8;
    await setTick("grid", true);
    const names = () =>
      last<Grid>("grid").features.flatMap((feature) => (feature.properties.name ? [feature.properties.name] : []));
    expect(names()).toContain(positionToLocator(60.2, 24.7).slice(0, 4));
    expect(last<Grid>("grid").features.some((feature) => feature.geometry.type === "LineString")).toBe(true);
    map.zoom = 12;
    map.bounds = { west: 24.7, south: 60.2, east: 24.8, north: 60.24 };
    map.fire("moveend");
    expect(names()).toContain(positionToLocator(60.22, 24.75));
    await setTick("grid", false);
    expect(last<Grid>("grid").features).toEqual([]);
  });

  it("is drawn from the start when it was ticked before the page was loaded", async () => {
    localStorage.setItem("NeoAPRS.layer.grid", "on");
    await mounted();
    expect((FakeMap.last().getSource("grid")?.data as Grid).features.length).toBeGreaterThan(0);
  });
});
