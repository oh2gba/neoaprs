import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { effectScope, nextTick, shallowRef, type EffectScope } from "vue";
import { useLayerTables, useLayerThings } from "@/composables/useLayerThings";
import { forgetLayerTicks, useMapLayers } from "@/composables/useMapLayers";
import type { Connection } from "@/lib/hub";
import type { Command, MapState } from "@/protocol/protocol";
import { NOW, ago, mapState } from "@/test/fixtures";
import { aircraft, layerThings, mapLayer, ship } from "@/test/layerfixtures";

let scope: EffectScope;

/** A page's traffic over parts a test changes: the topic `map` with aircraft from the own receiver and ships from Fintraffic, the socket open, the page in front, the replay closed. */
function make(layers = [mapLayer("aircraft", { source: "receiver" }), mapLayer("ships", { source: "fintraffic" })]) {
  const send = vi.fn((_command: Command) => true);
  const parts = {
    send,
    connection: shallowRef<Connection>("open"),
    visible: shallowRef(true),
    replay: shallowRef(false),
    map: shallowRef<MapState | null>(mapState({ layers })),
    now: shallowRef(NOW),
    store: useLayerTables(),
  };
  const run = scope.run(() => ({ traffic: useLayerThings(parts), ticks: useMapLayers(parts.map) }));
  if (!run) throw new Error("not made");
  return { ...parts, ...run, looks: () => send.mock.calls.map(([command]) => command) };
}

beforeEach(() => {
  localStorage.clear();
  forgetLayerTicks();
  scope = effectScope();
});
afterEach(() => {
  scope.stop();
  forgetLayerTicks();
});

describe("useLayerThings: when the page looks at a layer", () => {
  it("looks at nothing while no tick is on, and at a layer as soon as its tick is", () => {
    const page = make();
    expect(page.looks()).toEqual([]);
    page.ticks.setTicked("aircraft", true);
    expect(page.looks()).toEqual([{ cmd: "layer_look", layer: "aircraft", on: true }]);
    expect(page.traffic.looked.value).toEqual(["aircraft"]);
    page.ticks.setTicked("aircraft", false);
    expect(page.looks().at(-1)).toEqual({ cmd: "layer_look", layer: "aircraft", on: false });
  });

  it("looks from its first moment when the tick was on in this browser's memory", () => {
    localStorage.setItem("NeoAPRS.layer.ships", "on");
    expect(make().looks()).toEqual([{ cmd: "layer_look", layer: "ships", on: true }]);
  });

  it("does not look at a layer whose source is none, ticked or not, and looks once a source is chosen", () => {
    const page = make([mapLayer("aircraft"), mapLayer("ships")]);
    page.ticks.setTicked("aircraft", true);
    expect(page.looks()).toEqual([]);
    page.map.value = mapState({ layers: [mapLayer("aircraft", { source: "adsblol" }), mapLayer("ships")] });
    expect(page.looks()).toEqual([{ cmd: "layer_look", layer: "aircraft", on: true }]);
    page.map.value = mapState({ layers: [mapLayer("aircraft"), mapLayer("ships")] });
    expect(page.looks().at(-1)).toEqual({ cmd: "layer_look", layer: "aircraft", on: false });
  });

  it("stops looking while the page is behind and while the replay is open, and looks again after", () => {
    const page = make();
    page.ticks.setTicked("ships", true);
    page.visible.value = false;
    page.visible.value = true;
    page.replay.value = true;
    page.replay.value = false;
    expect(page.looks()).toEqual([
      { cmd: "layer_look", layer: "ships", on: true },
      { cmd: "layer_look", layer: "ships", on: false },
      { cmd: "layer_look", layer: "ships", on: true },
      { cmd: "layer_look", layer: "ships", on: false },
      { cmd: "layer_look", layer: "ships", on: true },
    ]);
  });

  it("says nothing on a closed socket, and looks again when it is opened anew", () => {
    const page = make();
    page.ticks.setTicked("aircraft", true);
    page.connection.value = "closed";
    page.connection.value = "connecting";
    page.connection.value = "open";
    expect(page.looks()).toEqual([
      { cmd: "layer_look", layer: "aircraft", on: true },
      { cmd: "layer_look", layer: "aircraft", on: true },
    ]);
  });
});

describe("useLayerThings: the tables", () => {
  it("keeps the latest table of a layer it looks at, and forgets it when the look ends", () => {
    const page = make();
    page.ticks.setTicked("aircraft", true);
    page.store.handlers.layerThings(layerThings("aircraft", [aircraft({ id: "a" })]));
    page.store.handlers.layerThings(layerThings("aircraft", [aircraft({ id: "b" })]));
    expect(page.traffic.tables.value.get("aircraft")?.things.map((thing) => thing.id)).toEqual(["b"]);
    page.ticks.setTicked("aircraft", false);
    expect(page.traffic.tables.value.size).toBe(0);
    expect(page.store.told.value.size).toBe(0);
    page.ticks.setTicked("aircraft", true);
    expect(page.traffic.tables.value.size).toBe(0); // (until the daemon tells it again)
  });

  it("counts no table of a layer it does not look at", () => {
    const page = make();
    page.store.handlers.layerThings(layerThings("ships", [ship()], { source: "fintraffic" }));
    expect(page.traffic.tables.value.size).toBe(0);
  });

  it("does not show, when it looks again, a table that came late after the last look ended", () => {
    const page = make();
    page.ticks.setTicked("aircraft", true);
    page.ticks.setTicked("aircraft", false);
    page.store.handlers.layerThings(layerThings("aircraft", [aircraft({ id: "late" })]));
    page.ticks.setTicked("aircraft", true);
    expect(page.traffic.tables.value.size).toBe(0);
    page.store.handlers.layerThings(layerThings("aircraft", [aircraft({ id: "new" })]));
    expect(page.traffic.tables.value.get("aircraft")?.things.map((thing) => thing.id)).toEqual(["new"]);
  });
});

describe("useLayerThings: the card of a thing", () => {
  it("opens one card at a time, the next thing's in place of the last", () => {
    const page = make();
    page.ticks.setTicked("aircraft", true);
    page.ticks.setTicked("ships", true);
    page.store.handlers.layerThings(layerThings("aircraft", [aircraft({ id: "a", at: ago(1) })]));
    page.store.handlers.layerThings(layerThings("ships", [ship({ id: "s", at: ago(1) })], { source: "fintraffic" }));
    page.traffic.open("aircraft", "a");
    expect(page.traffic.card.value).toMatchObject({ layer: "aircraft", source: "receiver", thing: { id: "a" } });
    page.traffic.open("ships", "s");
    expect(page.traffic.card.value).toMatchObject({ layer: "ships", source: "fintraffic", thing: { id: "s" } });
    expect(page.traffic.close()).toBe(true);
    expect(page.traffic.card.value).toBeNull();
    expect(page.traffic.close()).toBe(false);
  });

  it("follows its thing in each new table, and closes for good when the thing leaves it", async () => {
    const page = make();
    page.ticks.setTicked("aircraft", true);
    page.store.handlers.layerThings(layerThings("aircraft", [aircraft({ id: "a", lat: 60.3 })]));
    page.traffic.open("aircraft", "a");
    page.store.handlers.layerThings(layerThings("aircraft", [aircraft({ id: "a", lat: 60.31 })]));
    expect(page.traffic.card.value?.thing.lat).toBe(60.31);
    page.store.handlers.layerThings(layerThings("aircraft", []));
    await nextTick();
    expect(page.traffic.card.value).toBeNull();
    page.store.handlers.layerThings(layerThings("aircraft", [aircraft({ id: "a" })]));
    expect(page.traffic.card.value).toBeNull();
  });

  it("closes when its thing grows too old, and when the layer is no longer looked at", async () => {
    const page = make();
    page.ticks.setTicked("aircraft", true);
    page.store.handlers.layerThings(layerThings("aircraft", [aircraft({ id: "a", at: ago(30) })]));
    page.traffic.open("aircraft", "a");
    page.now.value = NOW + 31_000;
    await nextTick();
    expect(page.traffic.card.value).toBeNull();
    page.store.handlers.layerThings(layerThings("aircraft", [aircraft({ id: "b", at: ago(0) })]));
    page.traffic.open("aircraft", "b");
    page.ticks.setTicked("aircraft", false);
    expect(page.traffic.card.value).toBeNull();
  });

  it("opens nothing for a thing that is not in the tables", () => {
    const page = make();
    page.traffic.open("aircraft", "nowhere");
    expect(page.traffic.card.value).toBeNull();
  });
});
