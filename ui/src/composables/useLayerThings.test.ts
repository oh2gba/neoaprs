import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { effectScope, nextTick, shallowRef, type EffectScope } from "vue";
import { useLayerTables, useLayerThings } from "@/composables/useLayerThings";
import { forgetLayerTicks, useMapLayers } from "@/composables/useMapLayers";
import type { Connection } from "@/lib/hub";
import type { Command, MapState } from "@/protocol/protocol";
import { NOW, ago, mapState } from "@/test/fixtures";
import { aircraft, layerThings, mapLayer, ship } from "@/test/layerfixtures";

let scope: EffectScope;

/**
 * A page's traffic over parts a test changes: topic `map` with aircraft and ships, socket open,
 * page in front, replay closed.
 */
function make(layers = [mapLayer("aircraft", { source: "receiver" }), mapLayer("ships", { source: "fintraffic" })]) {
  const send = vi.fn((_command: Command) => true);
  const now = shallowRef(NOW);
  const parts = {
    send,
    connection: shallowRef<Connection>("open"),
    visible: shallowRef(true),
    replay: shallowRef(false),
    map: shallowRef<MapState | null>(mapState({ layers })),
    now,
    store: useLayerTables(() => now.value),
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

describe("useLayerThings: the trail of the thing whose card is open", () => {
  const seen = (
    page: ReturnType<typeof make>,
    id: string,
    lat: number,
    at: string,
    layer: "aircraft" | "ships" = "aircraft",
  ) =>
    page.store.handlers.layerThings(
      layerThings(
        layer,
        [layer === "aircraft" ? aircraft({ id, lat, at }) : ship({ id, lat, at })],
        layer === "ships" ? { source: "fintraffic" } : {},
      ),
    );

  it("has none without a card, and the places the open thing was seen at with one, beginning when the card's thing was first in a table", () => {
    const page = make();
    page.ticks.setTicked("aircraft", true);
    seen(page, "a", 60.1, ago(20));
    expect(page.traffic.trail.value).toEqual([]);
    seen(page, "a", 60.2, ago(10));
    page.traffic.open("aircraft", "a");
    seen(page, "a", 60.3, ago(5));
    expect(page.traffic.trail.value.map((point) => point[1])).toEqual([60.1, 60.2, 60.3]);
    page.traffic.close();
    expect(page.traffic.trail.value).toEqual([]);
  });

  it("does not add a point for a table that brings the same place", () => {
    const page = make();
    page.ticks.setTicked("aircraft", true);
    seen(page, "a", 60.1, ago(20));
    page.traffic.open("aircraft", "a");
    seen(page, "a", 60.1, ago(10));
    expect(page.traffic.trail.value).toHaveLength(1);
  });

  it("is the trail of the next thing when the card moves to it, ships included", () => {
    const page = make();
    page.ticks.setTicked("aircraft", true);
    page.ticks.setTicked("ships", true);
    seen(page, "a", 60.1, ago(5));
    seen(page, "s", 60.5, ago(5), "ships");
    seen(page, "s", 60.6, ago(2), "ships");
    page.traffic.open("aircraft", "a");
    expect(page.traffic.trail.value).toHaveLength(1);
    page.traffic.open("ships", "s");
    expect(page.traffic.trail.value.map((point) => point[1])).toEqual([60.5, 60.6]);
  });

  it("is kept when the thing leaves its table for a while, and goes on when it comes back", () => {
    const page = make();
    page.ticks.setTicked("aircraft", true);
    seen(page, "a", 60.1, ago(5));
    seen(page, "b", 60.1, ago(5));
    page.store.handlers.layerThings(layerThings("aircraft", [aircraft({ id: "b", lat: 60.2, at: ago(2) })]));
    seen(page, "a", 60.4, ago(1));
    page.traffic.open("aircraft", "a");
    expect(page.traffic.trail.value.map((point) => point[1])).toEqual([60.1, 60.4]);
  });

  it("survives the page going behind another tab, its tables emptied, and goes on when it is back", () => {
    const page = make();
    page.ticks.setTicked("aircraft", true);
    seen(page, "a", 60.1, ago(8));
    page.visible.value = false;
    expect(page.traffic.tables.value.size).toBe(0);
    page.visible.value = true;
    seen(page, "a", 60.2, ago(2));
    page.traffic.open("aircraft", "a");
    expect(page.traffic.trail.value.map((point) => point[1])).toEqual([60.1, 60.2]);
  });

  it("starts with what the daemon kept while the page was away", () => {
    const page = make();
    page.ticks.setTicked("aircraft", true);
    page.store.handlers.layerThings(
      layerThings("aircraft", [aircraft({ id: "a", lat: 60.3, lon: 24.9, at: ago(1) })], {
        trails: [
          {
            id: "a",
            points: [
              [24.9, 60.1, ago(90)],
              [24.9, 60.2, ago(30)],
            ],
          },
        ],
      }),
    );
    page.traffic.open("aircraft", "a");
    expect(page.traffic.trail.value.map((point) => point[1])).toEqual([60.1, 60.2, 60.3]);
  });

  it("is forgotten when the operator switches the layer off, and begins anew when it is on again", () => {
    const page = make();
    page.ticks.setTicked("aircraft", true);
    seen(page, "a", 60.1, ago(8));
    page.ticks.setTicked("aircraft", false);
    page.ticks.setTicked("aircraft", true);
    seen(page, "a", 60.2, ago(2));
    page.traffic.open("aircraft", "a");
    expect(page.traffic.trail.value.map((point) => point[1])).toEqual([60.2]);
  });
});
