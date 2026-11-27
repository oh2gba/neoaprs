import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { effectScope, shallowRef, type EffectScope } from "vue";
import { forgetLayerTicks, useMapLayers } from "@/composables/useMapLayers";
import { useSatelliteStore, useSatellites } from "@/composables/useSatellites";
import type { Connection } from "@/lib/hub";
import type { Command, MapState } from "@/protocol/protocol";
import { mapState } from "@/test/fixtures";
import { satelliteCard, satellitesMessage } from "@/test/satellitefixtures";

let scope: EffectScope;

/** A page's satellites layer over parts a test changes: socket open, page in front, replay closed. */
function make() {
  const send = vi.fn((_command: Command) => true);
  const store = useSatelliteStore();
  const parts = {
    send,
    connection: shallowRef<Connection>("open"),
    visible: shallowRef(true),
    replay: shallowRef(false),
    map: shallowRef<MapState | null>(mapState()),
    store,
  };
  const run = scope.run(() => ({ layer: useSatellites(parts), ticks: useMapLayers(parts.map) }));
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

describe("useSatellites: when the page looks", () => {
  it("looks at nothing while the tick is off, and from the tick on with the ids of its open cards", () => {
    const page = make();
    expect(page.looks()).toEqual([]);
    page.ticks.setTicked("satellites", true);
    expect(page.looks()).toEqual([{ cmd: "satellite_look", on: true, cards: [] }]);
    page.layer.open(25544);
    page.layer.open(59112);
    expect(page.looks().at(-1)).toEqual({ cmd: "satellite_look", on: true, cards: [25544, 59112] });
    page.layer.open(25544);
    expect(page.looks()).toHaveLength(3);
  });

  it("says off and forgets what it was told when the tick goes off, and its cards close", () => {
    const page = make();
    page.ticks.setTicked("satellites", true);
    page.layer.open(25544);
    page.store.handlers.satellites(satellitesMessage({ cards: [satelliteCard()] }));
    expect(page.layer.cards.value.map((card) => card.id)).toEqual([25544]);
    page.ticks.setTicked("satellites", false);
    expect(page.looks().at(-1)).toEqual({ cmd: "satellite_look", on: false, cards: [] });
    expect(page.layer.told.value).toBeNull();
    expect(page.layer.opened.value).toEqual([]);
  });

  it("looks again when the socket was opened anew and stops while the page is behind or the replay is open", () => {
    const page = make();
    page.ticks.setTicked("satellites", true);
    page.connection.value = "closed";
    page.connection.value = "open";
    expect(page.looks().at(-1)).toEqual({ cmd: "satellite_look", on: true, cards: [] });
    page.replay.value = true;
    expect(page.looks().at(-1)).toEqual({ cmd: "satellite_look", on: false, cards: [] });
    page.replay.value = false;
    page.visible.value = false;
    expect(page.layer.looked.value).toBe(false);
  });
});

describe("useSatellites: the cards", () => {
  it("are the told cards of the open ids, oldest first; Esc closes the newest and Close all the rest", () => {
    const page = make();
    page.ticks.setTicked("satellites", true);
    page.layer.open(59112);
    page.layer.open(25544);
    page.store.handlers.satellites(
      satellitesMessage({ cards: [satelliteCard(), satelliteCard({ id: 59112, name: "SONATE-2" })] }),
    );
    expect(page.layer.cards.value.map((card) => card.name)).toEqual(["SONATE-2", "ISS"]);
    expect(page.layer.close()).toBe(true);
    expect(page.layer.opened.value).toEqual([59112]);
    expect(page.layer.closeAll()).toBe(true);
    expect(page.layer.close()).toBe(false);
  });

  it("closes the card of a satellite that is no longer shown, and opens one alone on a phone", () => {
    const page = make();
    page.ticks.setTicked("satellites", true);
    page.layer.open(25544);
    page.layer.open(59112);
    page.store.handlers.satellites(satellitesMessage({ satellites: satellitesMessage().satellites.slice(1) }));
    expect(page.layer.opened.value).toEqual([59112]);
    page.layer.open(25544, true);
    expect(page.layer.opened.value).toEqual([25544]);
  });

  it("keeps its open cards through a hidden page, and shows them again when the daemon tells again", () => {
    const page = make();
    page.ticks.setTicked("satellites", true);
    page.layer.open(25544);
    page.store.handlers.satellites(satellitesMessage({ cards: [satelliteCard()] }));
    page.visible.value = false;
    expect(page.layer.cards.value).toEqual([]);
    page.visible.value = true;
    expect(page.looks().at(-1)).toEqual({ cmd: "satellite_look", on: true, cards: [25544] });
    page.store.handlers.satellites(satellitesMessage({ cards: [satelliteCard()] }));
    expect(page.layer.cards.value.map((card) => card.id)).toEqual([25544]);
  });
});
