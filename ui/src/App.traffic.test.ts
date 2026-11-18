import "@/test/mockmap";
import { describe, expect, it } from "vitest";
import { flushPromises } from "@vue/test-utils";
import { forgetLayerTicks } from "@/composables/useMapLayers";
import type { TrafficCollection } from "@/lib/layers/traffic";
import { FakeMap } from "@/test/fakemap";
import { open, tabButton, useAppHarness } from "@/test/app";
import { mapState } from "@/test/fixtures";
import { aircraft, layerThings, mapLayer, ship } from "@/test/layerfixtures";

useAppHarness();

const PLANE = aircraft({ id: "4ca1fe", name: "WALL123", registration: "OH-WAL" });
const BOAT = ship({ id: "230999111", name: "WALL STAR", destination: "NOWHERE" });
const WORDS = ["4ca1fe", "4CA1FE", "WALL123", "OH-WAL", "230999111", "WALL STAR", "NOWHERE"];

const drawn = (): string[] =>
  ((FakeMap.last().getSource("traffic")?.setData.mock.calls.at(-1)?.[0] as TrafficCollection | undefined)?.features ?? []).map(
    (feature) => feature.properties.id,
  );
const esc = () => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));

/** The page with the aircraft from the own receiver and the ships from Fintraffic ticked, and a table of each told. */
async function withTraffic() {
  forgetLayerTicks();
  localStorage.setItem("NeoAPRS.layer.aircraft", "on");
  localStorage.setItem("NeoAPRS.layer.ships", "on");
  const page = await open();
  FakeMap.last().fire("style.load");
  page.socket.say({
    type: "state",
    topic: "map",
    rev: 0,
    value: mapState({ layers: [mapLayer("aircraft", { source: "receiver" }), mapLayer("ships", { source: "fintraffic" })] }),
  });
  await flushPromises();
  page.socket.say(layerThings("aircraft", [PLANE]));
  page.socket.say(layerThings("ships", [BOAT], { source: "fintraffic" }));
  await flushPromises();
  return page;
}

async function clickThing(layer: string, id: string): Promise<void> {
  FakeMap.last().rendered = [{ layer: "traffic", properties: { layer, id } }];
  FakeMap.last().fire("click", { point: { x: 5, y: 5 }, lngLat: { lat: 60.3, lng: 24.9 }, originalEvent: new MouseEvent("click") });
  FakeMap.last().rendered = [];
  await flushPromises();
}

describe("App: the aircraft and ships on the map", () => {
  it("looks at each ticked layer that has a source, and draws what the daemon tells", async () => {
    const { wrapper, socket } = await withTraffic();
    expect(socket.sent).toContainEqual({ cmd: "layer_look", layer: "aircraft", on: true });
    expect(socket.sent).toContainEqual({ cmd: "layer_look", layer: "ships", on: true });
    expect(drawn()).toEqual(["4ca1fe", "230999111"]);
    wrapper.unmount();
  });

  it("opens a thing's card on a click, among the station cards, and Esc closes it with them", async () => {
    const { wrapper } = await withTraffic();
    await clickThing("aircraft", "4ca1fe");
    expect(document.querySelector(".cardstack .layercard .card-call")?.textContent?.trim()).toBe("WALL123");
    esc();
    await flushPromises();
    expect(document.querySelector(".layercard")).toBeNull();
    wrapper.unmount();
  });

  it("stops looking while the replay is open, and the things go from the map", async () => {
    const { wrapper, socket } = await withTraffic();
    FakeMap.last().fire("contextmenu", {
      lngLat: { lat: 60.1, lng: 24.9 },
      point: { x: 10, y: 10 },
      originalEvent: new MouseEvent("contextmenu", { clientX: 300, clientY: 200 }),
    });
    await flushPromises();
    document.querySelector<HTMLElement>(".mapmenu [role='menuitem'][data-item='replay']")?.click();
    await flushPromises();
    expect(socket.sent).toContainEqual({ cmd: "layer_look", layer: "aircraft", on: false });
    expect(socket.sent).toContainEqual({ cmd: "layer_look", layer: "ships", on: false });
    expect(drawn()).toEqual([]);
    wrapper.unmount();
  });

  it("puts nothing of them in any tab, the station cards' book, the Packets card or the statistics", async () => {
    const { wrapper } = await withTraffic();
    await clickThing("ships", "230999111");
    const tabs = ["Stations", "Nearby", "Packets", "Messages", "Bulletins", "Objects", "Settings"];
    for (const name of tabs) {
      const button = tabButton(wrapper, name);
      expect([name, button?.exists()]).toEqual([name, true]);
      await button?.trigger("click");
      await flushPromises();
      const panel = document.querySelector(".panel")?.textContent ?? "";
      expect(panel).not.toBe("");
      for (const word of WORDS) expect([name, panel.includes(word)]).toEqual([name, false]);
    }
    for (const item of ["stats", "packets"]) {
      FakeMap.last().fire("contextmenu", {
        lngLat: { lat: 60.1, lng: 24.9 },
        point: { x: 10, y: 10 },
        originalEvent: new MouseEvent("contextmenu", { clientX: 300, clientY: 200 }),
      });
      await flushPromises();
      document.querySelector<HTMLElement>(`.mapmenu [role='menuitem'][data-item='${item}']`)?.click();
      await flushPromises();
    }
    const overlays = [...document.querySelectorAll(".statscard, .packetscard")].map((card) => card.textContent ?? "").join(" ");
    expect(overlays).not.toBe("");
    for (const word of WORDS) expect(overlays.includes(word)).toBe(false);
    // the ship's card is the map's own, and the only place its name is on the page
    const named = [...document.querySelectorAll("body *")].filter((node) => node.children.length === 0 && node.textContent?.includes("WALL STAR"));
    expect(named.every((node) => node.closest(".layercard") !== null)).toBe(true);
    expect(named.length).toBe(1);
    wrapper.unmount();
  });
});
