import "@/test/mockmap";
import { flushPromises } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import { FakeMap, resetFakes } from "@/test/fakemap";
import { mountStationMap } from "@/test/stationmap";
import { tell } from "@/test/context";
import { NOW, mapState, radioRow, radiosTopic, station, table } from "@/test/fixtures";

type Ring = { features: { properties: { km: number; title: string }; geometry: { coordinates: number[][] } }[] };

const props = (extra = {}) => ({
  stations: table(station("OH2GBA", { is_me: true, lat: 60.17, lon: 24.94, symbol_code: "-" })),
  selected: null,
  focus: null,
  home: { lat: 60.17, lon: 24.94 },
  now: NOW,
  dark: false,
  aging: { timeouts: new Map(), defaultMin: 0 },
  ...extra,
});
const drawn = () => FakeMap.last().getSource("aloha")?.setData.mock.calls.at(-1)?.[0] as Ring;
const title = (wrapper: { find: (selector: string) => { attributes: (name: string) => string | undefined } }) => wrapper.find(".mapbox").attributes("title");

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

describe("the ALOHA circles", () => {
  it("has layers of its own, under the tracks and the route", async () => {
    await mounted();
    const layers = FakeMap.last().layers;
    expect(layers).toEqual(expect.arrayContaining(["aloha-halo", "aloha-line", "aloha-hit"]));
    expect(layers.indexOf("aloha-line")).toBeLessThan(layers.indexOf("tracks-line"));
    expect(layers.indexOf("aloha-line")).toBeLessThan(layers.indexOf("route-casing"));
  });

  it("is not drawn while the daemon tells no radius", async () => {
    const { daemon } = await mounted();
    expect(FakeMap.last().getSource("aloha")).toBeDefined();
    await tell(daemon, { map: mapState({ aloha: [] }) });
    expect(drawn().features).toEqual([]);
  });

  it("is drawn round our station when the daemon tells a radius, and again when it changes", async () => {
    const { daemon } = await mounted();
    await tell(daemon, { map: mapState({ aloha: [{ radio: 1, km: 42 }] }) });
    expect(drawn().features).toHaveLength(1);
    const first = drawn().features[0]?.geometry.coordinates ?? [];
    expect(first.length).toBeGreaterThan(60);
    await tell(daemon, { map: mapState({ aloha: [{ radio: 1, km: 80 }] }) });
    expect(drawn().features[0]?.geometry.coordinates[0]?.[1]).toBeGreaterThan(first[0]?.[1] ?? 0);
    await tell(daemon, { map: mapState({ aloha: [] }) });
    expect(drawn().features).toEqual([]);
  });

  it("is drawn from the start when the radius was known before the map was", async () => {
    const { daemon } = mountStationMap(props());
    await tell(daemon, { map: mapState({ aloha: [{ radio: 1, km: 30 }] }) });
    await flushPromises();
    FakeMap.last().fire("style.load");
    expect(FakeMap.last().sources.has("aloha")).toBe(true);
    expect(FakeMap.last().layers).toContain("aloha-line");
  });

  it("has its radius as a title while the pointer is on it, in the page's language", async () => {
    const { wrapper, daemon } = await mounted();
    await tell(daemon, { map: mapState({ aloha: [{ radio: 1, km: 42.4 }] }) });
    expect(title(wrapper)).toBeUndefined();
    FakeMap.last().fire("mouseenter", undefined, "aloha-hit");
    expect(title(wrapper)).toBe("ALOHA circle: 42 km");
    FakeMap.last().fire("mouseleave", undefined, "aloha-hit");
    expect(title(wrapper)).toBeUndefined();
  });

  it("gives a tenth of a kilometre below ten", async () => {
    const { wrapper, daemon } = await mounted();
    await tell(daemon, { map: mapState({ aloha: [{ radio: 1, km: 4.26 }] }) });
    FakeMap.last().fire("mouseenter", undefined, "aloha-hit");
    expect(title(wrapper)).toBe("ALOHA circle: 4.3 km");
  });

  it("is one for each radio the daemon worked one out for, in the map's one look, each naming its radio where several are on, the one under the pointer as the title", async () => {
    const { wrapper, daemon } = await mounted();
    await tell(daemon, { radios: radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury"), radioRow(3, "kiss", { number: 2 })) });
    await tell(daemon, {
      map: mapState({
        aloha: [
          { radio: 1, km: 42 },
          { radio: 3, km: 12.3 },
        ],
      }),
    });
    expect(drawn().features.map((feature) => feature.properties)).toEqual([
      { km: 42, title: "FM: ALOHA circle: 42 km" },
      { km: 12.3, title: "FM 2: ALOHA circle: 12 km" },
    ]);
    expect(FakeMap.last().layers.filter((layer) => layer.startsWith("aloha"))).toEqual(["aloha-halo", "aloha-line", "aloha-hit"]); // (one source, one look for all)
    FakeMap.last().fire("mousemove", { features: [{ properties: { title: "FM 2: ALOHA circle: 12 km" } }] }, "aloha-hit");
    expect(title(wrapper)).toBe("FM 2: ALOHA circle: 12 km");
    FakeMap.last().fire("mousemove", { features: [{ properties: { title: "FM: ALOHA circle: 42 km" } }] }, "aloha-hit");
    expect(title(wrapper)).toBe("FM: ALOHA circle: 42 km");
    FakeMap.last().fire("mouseleave", undefined, "aloha-hit");
    expect(title(wrapper)).toBeUndefined();
  });

  it("names no radio with one radio on", async () => {
    const { wrapper, daemon } = await mounted();
    await tell(daemon, { radios: radiosTopic(radioRow(1, "kenwood-tnc2")), map: mapState({ aloha: [{ radio: 1, km: 42 }] }) });
    expect(drawn().features.map((feature) => feature.properties.title)).toEqual(["ALOHA circle: 42 km"]);
    FakeMap.last().fire("mouseenter", { features: [{ properties: { title: "ALOHA circle: 42 km" } }] }, "aloha-hit");
    expect(title(wrapper)).toBe("ALOHA circle: 42 km");
  });
});
