import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { nextTick } from "vue";
import MapLayers from "@/components/MapLayers.vue";
import { forgetLayerTicks } from "@/composables/useMapLayers";
import { t } from "@/i18n";
import { MARKS } from "@/lib/layers/marks";
import { LAYER_TABLE, layerRows } from "@/lib/layers/table";
import { cssRule, mediaRule } from "@/test/css";
import { fakeDaemon, ofRadios, tell, withDaemon, type FakeDaemon, type Given } from "@/test/context";
import { mapState, radioRow } from "@/test/fixtures";
import { mapLayer } from "@/test/layerfixtures";
import type { MapLayer } from "@/protocol/protocol";

let place: HTMLElement;
let wrapper: VueWrapper | null = null;

function mounted(
  layers: MapLayer[] = [mapLayer("aircraft"), mapLayer("ships")],
  counts?: Record<string, number | null>,
  more: Given = {},
): { daemon: FakeDaemon } {
  const daemon = fakeDaemon({ map: mapState({ layers }), ...more });
  wrapper = mount(MapLayers, {
    props: { place, ...(counts ? { counts } : {}) },
    global: withDaemon(daemon),
    attachTo: document.body,
  });
  return { daemon };
}

const button = () => place.querySelector<HTMLButtonElement>(".layers-toggle");
const box = () => place.querySelector(".layers-box");
const rowIds = () => [...place.querySelectorAll<HTMLElement>(".layers-row")].map((row) => row.dataset["layer"]);
const row = (id: string) => place.querySelector<HTMLElement>(`.layers-row[data-layer="${id}"]`);
const tick = (id: string) => row(id)?.querySelector<HTMLInputElement>("input[type=checkbox]");

async function openBox(): Promise<void> {
  button()?.click();
  await nextTick();
}

beforeEach(() => {
  localStorage.clear();
  forgetLayerTicks();
  place = document.createElement("div");
  document.body.appendChild(place);
});

afterEach(() => {
  wrapper?.unmount();
  wrapper = null;
  place.remove();
});

describe("the Layers button", () => {
  it("stands in its place among the map's controls, with no text on the page and its one word as its name and title", () => {
    mounted();
    const toggle = button();
    expect(toggle).not.toBeNull();
    expect(toggle?.textContent?.trim()).toBe("");
    expect(toggle?.getAttribute("aria-label")).toBe("Layers");
    expect(toggle?.getAttribute("title")).toBe("Layers");
    expect(toggle?.getAttribute("aria-expanded")).toBe("false");
    expect(box()).toBeNull();
  });

  it("is not drawn before the map has its controls", () => {
    const daemon = fakeDaemon({ map: mapState() });
    wrapper = mount(MapLayers, { props: { place: null }, global: withDaemon(daemon), attachTo: document.body });
    expect(document.querySelector(".layers-toggle")).toBeNull();
  });

  it("answers to 40 px on a phone, as the zoom buttons do, by being a button of their group", () => {
    mounted();
    expect(button()?.closest(".layers")?.parentElement).toBe(place);
    expect(mediaRule("(pointer: coarse)", ".maplibregl-ctrl.maplibregl-ctrl-group button")).toMatch(/width:\s*40px/);
  });

  it("has rows a finger high on a touch screen, being ticks of the page's own kind", async () => {
    mounted();
    await openBox();
    expect(row("grid")?.classList.contains("check")).toBe(true);
    expect(mediaRule("(pointer: coarse)", ".check")).toMatch(/min-height:\s*40px/);
  });

  it("opens the box, and a second press, a press outside or Esc closes it, Esc giving the focus back to the button", async () => {
    mounted();
    await openBox();
    expect(box()).not.toBeNull();
    expect(button()?.getAttribute("aria-expanded")).toBe("true");
    button()?.click();
    await nextTick();
    expect(box()).toBeNull();

    await openBox();
    tick("tracks")?.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
    await nextTick();
    expect(box()).not.toBeNull(); // (a press inside leaves it open)
    document.body.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
    await nextTick();
    expect(box()).toBeNull();

    await openBox();
    tick("grid")?.focus();
    tick("grid")?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await nextTick();
    expect(box()).toBeNull();
    expect(document.activeElement).toBe(button());
  });
});

describe("the rows of the box", () => {
  it("are Tracks, ALOHA circle, Locator grid, Day and night and Satellites, each with its mark, and no row of things while the station has no source for them", async () => {
    mounted();
    await openBox();
    expect(rowIds()).toEqual(["tracks", "aloha", "grid", "daynight", "satellites"]);
    expect([...place.querySelectorAll(".layers-name")].map((name) => name.textContent)).toEqual([
      "Tracks",
      "ALOHA circle",
      "Locator grid",
      "Day and night",
      "Satellites",
    ]);
    expect(row("tracks")?.querySelector(".layermark path")?.getAttribute("d")).toBe(MARKS.track.d);
    expect(row("aloha")?.querySelector(".layermark path")?.getAttribute("stroke-dasharray")).toBe(MARKS.circle.dash);
    expect(row("grid")?.querySelector(".layermark path")?.getAttribute("d")).toBe(MARKS.grid.d);
    expect(place.querySelector(".layers-rule")).toBeNull();
  });

  it("have Aircraft and Ships under a thin line while the station has a source for them, the service's own name after the name and none for the own receiver", async () => {
    mounted([mapLayer("aircraft", { source: "adsbfi" }), mapLayer("ships", { source: "receiver" })]);
    await openBox();
    expect(rowIds()).toEqual(["tracks", "aloha", "grid", "daynight", "satellites", "aircraft", "ships"]);
    const rule = place.querySelector(".layers-rule");
    expect(rule?.nextElementSibling).toBe(row("aircraft"));
    expect(place.querySelectorAll(".layers-rule")).toHaveLength(1);
    expect(row("aircraft")?.querySelector(".layers-name")?.textContent).toBe("Aircraft");
    expect(row("aircraft")?.querySelector(".layers-source")?.textContent).toBe("adsb.fi");
    expect(row("aircraft")?.querySelector(".layermark path")?.getAttribute("d")).toBe(MARKS.airliner.d);
    expect(row("ships")?.querySelector(".layers-name")?.textContent).toBe("Ships");
    expect(row("ships")?.querySelector(".layers-source")).toBeNull();
    expect(row("ships")?.querySelector(".layermark path")?.getAttribute("d")).toBe(MARKS.hull.d);
  });

  it("give a Radarcape's aircraft no source word, as any own receiver", () => {
    expect(
      layerRows([mapLayer("aircraft", { source: "radarcape" }), mapLayer("ships")]).map((one) => one.source),
    ).toEqual([null, null, null, null, null, null]);
  });

  it("name adsb.lol and Fintraffic by their own names", () => {
    expect(
      layerRows([mapLayer("aircraft", { source: "adsblol" }), mapLayer("ships", { source: "fintraffic" })]).map(
        (one) => one.source,
      ),
    ).toEqual([null, null, null, null, null, "adsb.lol", "Fintraffic"]);
  });

  it("have no Aircraft row with the source none, and no row of things from a daemon that tells no layers", () => {
    expect(layerRows([mapLayer("aircraft"), mapLayer("ships", { source: "fintraffic" })]).map((one) => one.id)).toEqual(
      ["tracks", "aloha", "grid", "daynight", "satellites", "ships"],
    );
    expect(layerRows([]).map((one) => one.id)).toEqual(["tracks", "aloha", "grid", "daynight", "satellites"]);
    expect(layerRows(undefined).map((one) => one.id)).toEqual(["tracks", "aloha", "grid", "daynight", "satellites"]);
  });

  it("have Day and night after Locator grid on every station, with a radio of any kind or none", async () => {
    const rowsOf = async (given: Given) => {
      mounted(undefined, undefined, given);
      await openBox();
      const ids = rowIds();
      wrapper?.unmount();
      return ids;
    };
    expect(await rowsOf(ofRadios())).toEqual(["tracks", "aloha", "grid", "daynight", "satellites"]);
    expect(await rowsOf(ofRadios(radioRow(1, "kenwood-tnc2")))).toEqual([
      "tracks",
      "aloha",
      "grid",
      "daynight",
      "satellites",
    ]);
    mounted(undefined, undefined, ofRadios(radioRow(2, "dummy-hf")));
    await openBox();
    expect(rowIds()).toEqual(["tracks", "aloha", "grid", "daynight", "satellites"]);
    expect(row("daynight")?.querySelector(".layers-name")?.textContent).toBe("Day and night");
    expect(row("daynight")?.querySelector(".layermark path")?.getAttribute("d")).toBe(MARKS.daynight.d);
    expect(row("daynight")?.querySelector(".layers-source")).toBeNull();
    expect(row("daynight")?.querySelector(".layers-count")).toBeNull();
    expect(place.querySelector(".layers-rule")).toBeNull();
  });

  it("have Day and night before the thin line", async () => {
    mounted([mapLayer("aircraft", { source: "adsbfi" })]);
    await openBox();
    expect(rowIds()).toEqual(["tracks", "aloha", "grid", "daynight", "satellites", "aircraft"]);
    expect(place.querySelector(".layers-rule")?.nextElementSibling).toBe(row("aircraft"));
  });

  it("do not come and go while the box is open: they follow the station when it opens again", async () => {
    const { daemon } = mounted();
    await openBox();
    await tell(daemon, {
      map: mapState({ layers: [mapLayer("aircraft", { source: "receiver" }), mapLayer("ships")] }),
    });
    expect(rowIds()).toEqual(["tracks", "aloha", "grid", "daynight", "satellites"]);
    button()?.click();
    await nextTick();
    await openBox();
    expect(rowIds()).toEqual(["tracks", "aloha", "grid", "daynight", "satellites", "aircraft"]);
  });

  it("keep the room of a count at one width in tabular figures on every row of things: a number, a dash while away, nothing while off", async () => {
    mounted([mapLayer("aircraft", { source: "adsbfi" }), mapLayer("ships", { source: "fintraffic" })], {
      aircraft: 1043,
    });
    await openBox();
    expect(row("aircraft")?.querySelector(".layers-count")?.textContent).toBe("1043");
    expect(row("ships")?.querySelector(".layers-count")?.textContent).toBe("");
    expect(row("tracks")?.querySelector(".layers-count")).toBeNull();
    await wrapper?.setProps({ counts: { aircraft: null, ships: 7 } });
    expect(row("aircraft")?.querySelector(".layers-count")?.textContent).toBe("–");
    expect(row("ships")?.querySelector(".layers-count")?.textContent).toBe("7");
    expect(cssRule(".layers-count")).toMatch(/min-width:\s*4ch/);
    expect(cssRule(".layers-count")).toMatch(/font-variant-numeric:\s*tabular-nums/);
    expect(cssRule(".layers-count")).toMatch(/flex:\s*none/);
  });

  it("fit the box on a phone (375 px) in English, the longest with its source and its count", () => {
    // The box beside the button has 375 - 10 - 40 - 8 - 16 = 301 px; a row less its padding, tick,
    // mark and gaps has 245 px for its words, about 28 characters at 14 px, and a row of things
    // after its source and its count has 245 - 8 - 4ch - 8 about 26 characters for its name and
    // source.
    for (const entry of LAYER_TABLE) {
      const words = t(entry.name);
      expect(words.length, words).toBeLessThanOrEqual(entry.part === "own" ? 28 : 26 - "Fintraffic".length);
    }
    expect(cssRule(".layers-box")).toMatch(/max-width:\s*calc\(100vw - 80px\)/);
  });
});

describe("the ticks", () => {
  it("are Tracks and ALOHA circle on out of the box, the rest off", async () => {
    mounted([mapLayer("aircraft", { source: "receiver" }), mapLayer("ships", { source: "receiver" })]);
    await openBox();
    expect(["tracks", "aloha", "grid", "aircraft", "ships"].map((id) => tick(id)?.checked)).toEqual([
      true,
      true,
      false,
      false,
      false,
    ]);
  });

  it("are off for Day and night out of the box, and its tick is this browser's", async () => {
    mounted();
    await openBox();
    expect(tick("daynight")?.checked).toBe(false);
    tick("daynight")?.click();
    await nextTick();
    expect(localStorage.getItem("NeoAPRS.layer.daynight")).toBe("on");
    expect(tick("daynight")?.checked).toBe(true);
  });

  it("are this browser's, and there again after a reload", async () => {
    mounted([mapLayer("aircraft", { source: "receiver" }), mapLayer("ships")]);
    await openBox();
    tick("tracks")?.click();
    tick("grid")?.click();
    tick("aircraft")?.click();
    await nextTick();
    expect(localStorage.getItem("NeoAPRS.layer.tracks")).toBe("off");
    expect(localStorage.getItem("NeoAPRS.layer.grid")).toBe("on");
    expect(localStorage.getItem("NeoAPRS.layer.aircraft")).toBe("on");
    wrapper?.unmount();
    forgetLayerTicks(); // (a reload)
    mounted([mapLayer("aircraft", { source: "receiver" }), mapLayer("ships")]);
    await openBox();
    expect(["tracks", "aloha", "grid", "aircraft"].map((id) => tick(id)?.checked)).toEqual([false, true, true, true]);
  });
});
