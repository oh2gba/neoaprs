import "@/test/mockmap";
import { flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { forgetLayerTicks } from "@/composables/useMapLayers";
import { AIRCRAFT_SHAPES } from "@/lib/layers/aircraftshapes";
import { THING_SHAPES, type TrafficCollection } from "@/lib/layers/traffic";
import { FakeMap, resetFakes } from "@/test/fakemap";
import { tell, type FakeDaemon } from "@/test/context";
import { mountStationMap } from "@/test/stationmap";
import { NOW, ago, mapState, station, table } from "@/test/fixtures";
import { aircraft, layerThings, mapLayer, ship } from "@/test/layerfixtures";
import type { MapLayer } from "@/protocol/protocol";

const props = () => ({
  stations: table(station("OH2GBA", { is_me: true, lat: 60.17, lon: 24.94, symbol_code: "-" })),
  selected: null,
  focus: null,
  home: { lat: 60.17, lon: 24.94 },
  now: NOW,
  dark: false,
  aging: { defaultMin: 0 },
});

const SOURCES: MapLayer[] = [mapLayer("aircraft", { source: "adsbfi" }), mapLayer("ships", { source: "fintraffic" })];
const drawn = (): TrafficCollection =>
  FakeMap.last().getSource("traffic")?.setData.mock.calls.at(-1)?.[0] as TrafficCollection;
const drawnIds = () => drawn().features.map((feature) => feature.properties.id);
const control = () => FakeMap.last().controls.find((box) => box.classList.contains("layers-ctrl"));
const hovercard = () => document.querySelector<HTMLElement>(".hovercard");

async function mounted(layers: MapLayer[] = SOURCES) {
  const made = mountStationMap(props());
  await flushPromises();
  FakeMap.last().fire("style.load");
  await tell(made.daemon, { map: mapState({ layers }) });
  return made;
}

async function setTick(id: string, on: boolean): Promise<void> {
  if (!control()?.querySelector(".layers-box")) control()?.querySelector<HTMLButtonElement>(".layers-toggle")?.click();
  await nextTick();
  const box = control()?.querySelector<HTMLInputElement>(`.layers-row[data-layer="${id}"] input`);
  if (box && box.checked !== on) box.click();
  await nextTick();
}

async function told(daemon: FakeDaemon, ...tables: ReturnType<typeof layerThings>[]): Promise<void> {
  for (const one of tables) daemon.layerTables.handlers.layerThings(one);
  await nextTick();
}

function click(point = { x: 5, y: 5 }): void {
  FakeMap.last().fire("click", { point, lngLat: { lat: 60.3, lng: 24.9 }, originalEvent: new MouseEvent("click") });
}

beforeEach(() => {
  resetFakes();
  localStorage.clear();
  forgetLayerTicks();
});
afterEach(() => {
  vi.useRealTimers();
  document.body.replaceChildren();
});

describe("the aircraft and ships on the map", () => {
  it("lie over the grid and the circles and under the tracks and the route", async () => {
    await mounted();
    const layers = FakeMap.last().layers;
    expect(layers.indexOf("traffic")).toBeGreaterThan(layers.indexOf("aloha-line"));
    expect(layers.indexOf("traffic")).toBeGreaterThan(layers.indexOf("grid-names"));
    expect(layers.indexOf("traffic")).toBeLessThan(layers.indexOf("tracks-line"));
  });

  it("have their names in a layer of their own under the base map's names, which give way to those and to each other from zoom 10", async () => {
    await mounted();
    const map = FakeMap.last();
    const style = map.getStyle().layers;
    const firstBaseName = style.find((layer) => layer.type === "symbol" && !map.layers.includes(layer.id))?.id;
    expect(firstBaseName).toBeDefined();
    expect(style.findIndex((layer) => layer.id === "traffic-names")).toBeLessThan(
      style.findIndex((layer) => layer.id === firstBaseName),
    );
    const names = map.specs.get("traffic-names");
    expect(names?.minzoom).toBe(10);
    expect(names?.layout).toMatchObject({ "text-field": ["get", "name"] });
    const offset = JSON.stringify(names?.layout?.["text-offset"]);
    expect(offset).toContain('["get","side"]');
    for (const [side, drop] of [
      [16, 0.9],
      [26, 1.35],
      [30, 1.54],
      [17, 0.95],
    ] as const)
      expect(offset, `${side}`).toContain(`${side},["literal",[0,${drop}]]`);
    for (const free of ["text-ignore-placement", "text-allow-overlap"]) expect(names?.layout?.[free]).toBeUndefined();
    const marks = map.specs.get("traffic");
    expect(marks?.layout?.["text-field"]).toBeUndefined();
    expect(marks?.layout).toMatchObject({ "icon-allow-overlap": true, "icon-ignore-placement": true });
  });

  it("are drawn with the images the map is given with its layers, again at every new style (the colour scheme changed)", async () => {
    const drawnWith: string[] = [];
    const context = {
      scale: vi.fn(),
      translate: vi.fn(),
      stroke: vi.fn(),
      fill: vi.fn(() => drawnWith.push(String(context.fillStyle))),
      getImageData: vi.fn((_x: number, _y: number, w: number, h: number) => ({
        width: w,
        height: h,
        data: new Uint8ClampedArray(w * h * 4),
      })),
      fillStyle: "",
      strokeStyle: "",
      lineWidth: 0,
      lineJoin: "",
    };
    vi.stubGlobal("Path2D", class {});
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context as unknown as CanvasRenderingContext2D);
    await mounted();
    expect([...FakeMap.last().images.keys()].sort()).toEqual(
      THING_SHAPES.flatMap((shape) => [`traffic-${shape}`, `traffic-${shape}-bad`]).sort(),
    );
    expect(THING_SHAPES).toHaveLength(13);
    expect(FakeMap.last().images.get("traffic-diamond")).toMatchObject({ width: 32, height: 32 });
    expect(FakeMap.last().images.get("traffic-heavy4")).toMatchObject({
      width: 2 * AIRCRAFT_SHAPES.heavy4.size,
      height: 2 * AIRCRAFT_SHAPES.heavy4.size,
    });
    expect(FakeMap.last().images.get("traffic-balloon")).toMatchObject({ width: 2 * AIRCRAFT_SHAPES.balloon.size });
    const before = drawnWith.length;
    FakeMap.last().fire("style.load");
    expect(drawnWith.length).toBe(before + 26);
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("are looked at while their row's tick is on, and drawn from the tables the daemon tells", async () => {
    const { daemon } = await mounted();
    expect(daemon.send).not.toHaveBeenCalledWith({ cmd: "layer_look", layer: "aircraft", on: true });
    await setTick("aircraft", true);
    expect(daemon.send).toHaveBeenCalledWith({ cmd: "layer_look", layer: "aircraft", on: true });
    await told(
      daemon,
      layerThings("aircraft", [aircraft({ id: "a" }), aircraft({ id: "b", heading_deg: null })], { source: "adsbfi" }),
    );
    expect(drawnIds()).toEqual(["a", "b"]);
    expect(drawn().features.map((feature) => feature.properties.icon)).toEqual(["traffic-airliner", "traffic-diamond"]);
    await setTick("aircraft", false);
    expect(daemon.send).toHaveBeenCalledWith({ cmd: "layer_look", layer: "aircraft", on: false });
    expect(drawnIds()).toEqual([]);
  });

  it("are dropped by their age as the clock moves on, between two tables", async () => {
    const { daemon } = await mounted();
    await setTick("ships", true);
    await told(
      daemon,
      layerThings("ships", [ship({ id: "old", at: ago(1790) }), ship({ id: "new", at: ago(10) })], {
        source: "fintraffic",
      }),
    );
    expect(drawnIds()).toEqual(["old", "new"]);
    await tell(daemon, { now: NOW + 20_000 });
    expect(drawnIds()).toEqual(["new"]);
  });

  it("go while the replay is open, which does not look at them", async () => {
    const { daemon } = await mounted();
    await setTick("aircraft", true);
    await told(daemon, layerThings("aircraft", [aircraft()], { source: "adsbfi" }));
    daemon.replayOpen.value = true;
    await nextTick();
    expect(daemon.send).toHaveBeenLastCalledWith({ cmd: "layer_look", layer: "aircraft", on: false });
    expect(drawnIds()).toEqual([]);
  });

  it("count in their row of the Layers box what is drawn, with a dash while the source is away", async () => {
    const { daemon } = await mounted();
    await setTick("aircraft", true);
    const count = () => control()?.querySelector('.layers-row[data-layer="aircraft"] .layers-count')?.textContent;
    expect(count()).toBe("");
    await told(
      daemon,
      layerThings("aircraft", [aircraft({ id: "a" }), aircraft({ id: "b" }), aircraft({ id: "c" })], {
        source: "adsbfi",
      }),
    );
    control()?.querySelector<HTMLButtonElement>(".layers-toggle")?.click();
    await nextTick();
    control()?.querySelector<HTMLButtonElement>(".layers-toggle")?.click();
    await nextTick();
    expect(count()).toBe("3");
    await told(daemon, layerThings("aircraft", [aircraft({ id: "a" })], { source: "adsbfi", away: true }));
    expect(count()).toBe("–");
  });
});

describe("a click on an aircraft or a ship", () => {
  it("opens its card and leaves the station cards as they are; a click elsewhere closes it and lets go of the stations", async () => {
    const { wrapper, daemon } = await mounted();
    await setTick("aircraft", true);
    await told(daemon, layerThings("aircraft", [aircraft({ id: "a" })], { source: "adsbfi" }));
    FakeMap.last().rendered = [{ layer: "traffic", properties: { layer: "aircraft", id: "a", key: "aircraft:a" } }];
    click();
    expect(daemon.traffic.card.value).toMatchObject({ layer: "aircraft", thing: { id: "a" } });
    expect(wrapper.emitted("select")).toBeUndefined();
    FakeMap.last().rendered = [];
    click();
    expect(daemon.traffic.card.value).toBeNull();
    expect(wrapper.emitted("select")).toEqual([[null]]);
  });

  it("reaches a mark a finger nearly touched: the map is asked for what lies 6 px round the point, and the topmost found is opened", async () => {
    const { daemon } = await mounted();
    await setTick("aircraft", true);
    await told(daemon, layerThings("aircraft", [aircraft({ id: "a" }), aircraft({ id: "b" })], { source: "adsbfi" }));
    FakeMap.last().rendered = [
      { layer: "traffic", properties: { layer: "aircraft", id: "b" } },
      { layer: "traffic", properties: { layer: "aircraft", id: "a" } },
    ];
    click({ x: 100, y: 40 });
    expect(FakeMap.last().queried.at(-1)).toEqual([
      [94, 34],
      [106, 46],
    ]);
    expect(daemon.traffic.card.value).toMatchObject({ thing: { id: "b" } });
  });

  it("is a place while the first-run guide asks for one", async () => {
    const { wrapper, daemon } = await mounted();
    await setTick("aircraft", true);
    await told(daemon, layerThings("aircraft", [aircraft({ id: "a" })], { source: "adsbfi" }));
    await wrapper.setProps({ picking: true });
    FakeMap.last().rendered = [{ layer: "traffic", properties: { layer: "aircraft", id: "a" } }];
    click();
    expect(daemon.traffic.card.value).toBeNull();
    expect(wrapper.emitted("pick")).toHaveLength(1);
  });
});

describe("the trail of the thing whose card is open", () => {
  type Drawn = { features: { properties: { call: string }; geometry: { coordinates: number[][] } }[] };
  const trail = (): Drawn | undefined => {
    const last: unknown = FakeMap.last().getSource("traffic-trail")?.setData.mock.calls.at(-1)?.[0];
    return last as Drawn | undefined;
  };

  it("is drawn under the marks for the open card's thing only, one update when a table comes, and gone when the card closes", async () => {
    const { daemon } = await mounted();
    await setTick("aircraft", true);
    await told(
      daemon,
      layerThings(
        "aircraft",
        [aircraft({ id: "a", lat: 60.1, at: ago(20) }), aircraft({ id: "b", lat: 60.5, at: ago(20) })],
        { source: "adsbfi" },
      ),
    );
    const layers = FakeMap.last()
      .getStyle()
      .layers.map((layer) => layer.id);
    expect(layers.indexOf("traffic-trail")).toBeGreaterThan(layers.indexOf("aloha-line"));
    expect(layers.indexOf("traffic-trail")).toBeLessThan(layers.indexOf("traffic"));
    expect(trail()).toBeUndefined();
    daemon.traffic.open("aircraft", "a");
    await nextTick();
    expect(trail()?.features).toEqual([]);
    await told(
      daemon,
      layerThings(
        "aircraft",
        [aircraft({ id: "a", lat: 60.2, at: ago(10) }), aircraft({ id: "b", lat: 60.6, at: ago(10) })],
        { source: "adsbfi" },
      ),
    );
    const calls = FakeMap.last().getSource("traffic-trail")?.setData.mock.calls.length ?? 0;
    expect(trail()?.features.map((feature) => feature.properties.call)).toEqual(["aircraft:a"]);
    expect(trail()?.features[0]?.geometry.coordinates.map((point) => point[1])).toEqual([60.1, 60.2]);
    await told(daemon, layerThings("aircraft", [aircraft({ id: "a", lat: 60.3, at: ago(5) })], { source: "adsbfi" }));
    expect(FakeMap.last().getSource("traffic-trail")?.setData.mock.calls.length).toBe(calls + 1);
    await tell(daemon, { now: NOW + 5_000 });
    await tell(daemon, { now: NOW + 10_000 });
    expect(FakeMap.last().getSource("traffic-trail")?.setData.mock.calls.length).toBe(calls + 1);
    daemon.traffic.close();
    await nextTick();
    expect(trail()?.features).toEqual([]);
  });
});

describe("a mouse resting on an aircraft or a ship", () => {
  function rest(layer: string, id: string, pointerType = "mouse"): void {
    const event = new Event("pointermove");
    Object.defineProperty(event, "pointerType", { value: pointerType });
    FakeMap.last().getContainer().dispatchEvent(event);
    FakeMap.last().fire("mousemove", { features: [{ properties: { layer, id } }] }, "traffic");
  }

  it("shows the page's hover box after the delay, with what the source says, and it goes when the mouse leaves", async () => {
    const { daemon } = await mounted();
    await setTick("aircraft", true);
    await told(daemon, layerThings("aircraft", [aircraft({ id: "a", at: ago(4) })], { source: "adsbfi" }));
    vi.useFakeTimers();
    rest("aircraft", "a");
    vi.advanceTimersByTime(100);
    rest("aircraft", "a"); // (the mouse moves on the same mark: the delay goes on)
    expect(hovercard()?.hidden).toBe(true);
    vi.advanceTimersByTime(200);
    expect(hovercard()?.hidden).toBe(false);
    expect(hovercard()?.querySelector(".hc-call")?.textContent).toBe("FIN7AB");
    expect([...(hovercard()?.querySelectorAll(".hc-key") ?? [])].map((key) => key.textContent)).toEqual([
      "Altitude",
      "Speed",
      "Age",
    ]);
    FakeMap.last().fire("mouseleave", {}, "traffic");
    expect(hovercard()?.hidden).toBe(true);
  });

  it("shows the aircraft's own shape before its name, in the bad colour for an emergency, and a ship's hull", async () => {
    const { daemon } = await mounted();
    await setTick("aircraft", true);
    await setTick("ships", true);
    await told(
      daemon,
      layerThings(
        "aircraft",
        [aircraft({ id: "h", category: "A7", designator: "", heading_deg: null, emergency: true, at: ago(4) })],
        { source: "adsbfi" },
      ),
      layerThings("ships", [ship({ id: "s", at: ago(4) })], { source: "fintraffic" }),
    );
    vi.useFakeTimers();
    rest("aircraft", "h");
    vi.advanceTimersByTime(300);
    const mark = () => hovercard()?.querySelector(".hc-head > svg.hc-mark");
    expect(mark()?.querySelector("path")?.getAttribute("d")).toBe(AIRCRAFT_SHAPES.helicopter.d);
    expect(mark()?.getAttribute("viewBox")).toBe(AIRCRAFT_SHAPES.helicopter.viewBox);
    expect(mark()?.classList.contains("emergency")).toBe(true);
    expect(mark()?.getAttribute("aria-hidden")).toBe("true");
    FakeMap.last().fire("mouseleave", {}, "traffic");
    rest("ships", "s");
    vi.advanceTimersByTime(300);
    expect(mark()?.classList.contains("emergency")).toBe(false);
    expect(mark()?.getAttribute("viewBox")).toBe("0 0 16 16");
  });

  it("shows nothing for a finger: a tap opens the card", async () => {
    const { daemon } = await mounted();
    await setTick("ships", true);
    await told(daemon, layerThings("ships", [ship({ id: "s", at: ago(4) })], { source: "fintraffic" }));
    vi.useFakeTimers();
    rest("ships", "s", "touch");
    vi.advanceTimersByTime(1000);
    expect(hovercard()?.hidden).toBe(true);
  });
});

describe("the credit of the aircraft's shapes", () => {
  const shapes = () => document.querySelector<HTMLElement>(".attrib-shapes")?.textContent ?? null;

  it("is in the map's (i) while aircraft are drawn, from a service or an own receiver, and goes when their tick is off", async () => {
    await mounted([mapLayer("aircraft", { source: "radarcape" }), mapLayer("ships", { source: "fintraffic" })]);
    document.querySelector<HTMLButtonElement>(".attrib-toggle")?.click();
    await nextTick();
    expect(shapes()).toBeNull();
    await setTick("ships", true);
    expect(shapes()).toBeNull();
    await setTick("aircraft", true);
    expect(shapes()).toBe("Aircraft shapes: tar1090 by Matthias Wirth (github.com/wiedehopf/tar1090), GPL 2 or later");
    await setTick("aircraft", false);
    expect(shapes()).toBeNull();
  });
});

describe("the credits of a service", () => {
  const credits = () => [...document.querySelectorAll<HTMLElement>(".attrib-layer")];
  async function openCredits(): Promise<void> {
    document.querySelector<HTMLButtonElement>(".attrib-toggle")?.click();
    await nextTick();
  }

  it("are in the map's (i) while its layer is drawn, with their links opening in a new tab, and go when the tick is off", async () => {
    await mounted();
    await openCredits();
    expect(credits()).toEqual([]);
    await setTick("ships", true);
    expect(credits().map((line) => line.textContent)).toEqual([
      "Source: Fintraffic / digitraffic.fi, license CC 4.0 BY",
    ]);
    const links = [...(credits()[0]?.querySelectorAll("a") ?? [])];
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "https://www.digitraffic.fi/",
      "https://creativecommons.org/licenses/by/4.0/",
    ]);
    expect(links.every((link) => link.target === "_blank" && link.rel.includes("noopener"))).toBe(true);
    await setTick("aircraft", true);
    expect(credits().map((line) => line.dataset.source)).toEqual(["adsbfi", "fintraffic"]);
    await setTick("ships", false);
    await setTick("aircraft", false);
    expect(credits()).toEqual([]);
  });

  it("are owed by no own receiver", async () => {
    await mounted([mapLayer("aircraft", { source: "receiver" }), mapLayer("ships", { source: "receiver" })]);
    await openCredits();
    await setTick("aircraft", true);
    await setTick("ships", true);
    expect(credits()).toEqual([]);
  });

  it("name adsb.lol's licence with its link", async () => {
    await mounted([mapLayer("aircraft", { source: "adsblol" }), mapLayer("ships")]);
    await openCredits();
    await setTick("aircraft", true);
    expect(credits().map((line) => line.textContent)).toEqual(["adsb.lol, ODbL 1.0"]);
    expect([...(credits()[0]?.querySelectorAll("a") ?? [])].map((link) => link.getAttribute("href"))).toEqual([
      "https://www.adsb.lol/",
      "https://opendatacommons.org/licenses/odbl/1-0/",
    ]);
  });
});
