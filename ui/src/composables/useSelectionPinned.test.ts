import { describe, expect, it, vi } from "vitest";
import { nextTick, ref, shallowRef } from "vue";
import { useSelection } from "@/composables/useSelection";
import type { StationRow } from "@/protocol/protocol";
import { station } from "@/test/fixtures";

const CALLS = ["OH2ZWA", "OH2ZWB", "OH2ZWC", "OH2ZWD", "OH2ZWE"];
const all = (): ReadonlyMap<string, StationRow> => new Map(CALLS.map((call) => [call, station(call)] as const));

function setUp(capacity = 4, pinned: string[] = [], told = true) {
  const stations = shallowRef<ReadonlyMap<string, StationRow>>(all());
  const room = ref(capacity);
  const pinsOn = ref(true);
  const ready = ref(told);
  const pins = ref<string[]>(pinned);
  return {
    stations,
    room,
    pinsOn,
    ready,
    pins,
    picked: useSelection(
      stations,
      vi.fn(() => true),
      room,
      { pinned: pins, pinsOn, ready },
    ),
  };
}

describe("useSelection with pinned cards", () => {
  it("pins an open card, and only an open card; the pin can be taken away, and the card stays", () => {
    const { picked } = setUp();
    picked.pin("OH2ZWA", true);
    expect(picked.pinned.value).toEqual([]);
    picked.pick("OH2ZWA");
    picked.pin("OH2ZWA", true);
    picked.pin("OH2ZWA", true);
    expect(picked.pinned.value).toEqual(["OH2ZWA"]);
    picked.pin("OH2ZWA", false);
    expect([picked.pinned.value, picked.open.value]).toEqual([[], ["OH2ZWA"]]);
  });

  it("keeps a pinned card when another station is picked, with or without Ctrl, and closes the unpinned ones", () => {
    const { picked } = setUp();
    picked.pick("OH2ZWA");
    picked.pin("OH2ZWA", true);
    picked.pick("OH2ZWB", true);
    picked.pick("OH2ZWC");
    expect(picked.open.value).toEqual(["OH2ZWA", "OH2ZWC"]);
    expect(picked.selected.value).toBe("OH2ZWC");
    picked.pick("OH2ZWD", true);
    picked.pick("OH2ZWE");
    expect(picked.open.value).toEqual(["OH2ZWA", "OH2ZWE"]);
  });

  it("does not close a pinned card on a Ctrl+click of its station: it is the newest then", () => {
    const { picked } = setUp();
    picked.pick("OH2ZWA");
    picked.pin("OH2ZWA", true);
    picked.pick("OH2ZWB", true);
    expect(picked.pick("OH2ZWA", true)).toBe(true);
    expect(picked.open.value).toEqual(["OH2ZWB", "OH2ZWA"]);
    expect(picked.pick("OH2ZWB", true)).toBe(false);
    expect(picked.open.value).toEqual(["OH2ZWA"]);
  });

  it("closes only the cards that are not pinned on Esc and Close all, and says whether it closed any", () => {
    const { picked } = setUp();
    picked.pick("OH2ZWA");
    picked.pick("OH2ZWB", true);
    picked.pick("OH2ZWC", true);
    picked.pin("OH2ZWB", true);
    expect(picked.closeAll()).toBe(true);
    expect(picked.open.value).toEqual(["OH2ZWB"]);
    expect(picked.closeAll()).toBe(false);
    expect(picked.open.value).toEqual(["OH2ZWB"]);
    expect(picked.selected.value).toBe("OH2ZWB");
  });

  it("closes a pinned card with its cross, and it is not pinned any more", () => {
    const { picked } = setUp();
    picked.pick("OH2ZWA");
    picked.pin("OH2ZWA", true);
    picked.close("OH2ZWA");
    expect([picked.open.value, picked.pinned.value]).toEqual([[], []]);
  });

  it("never closes a pinned card for room: the oldest card that is not pinned goes, and the newest stays", async () => {
    const { room, picked } = setUp(3);
    picked.pick("OH2ZWA");
    picked.pin("OH2ZWA", true);
    picked.pick("OH2ZWB", true);
    picked.pick("OH2ZWC", true);
    picked.pick("OH2ZWD", true);
    expect(picked.open.value).toEqual(["OH2ZWA", "OH2ZWC", "OH2ZWD"]);
    room.value = 1;
    await nextTick();
    expect(picked.open.value).toEqual(["OH2ZWA", "OH2ZWD"]);
    picked.pin("OH2ZWD", true);
    picked.pick("OH2ZWE", true);
    expect(picked.open.value).toEqual(["OH2ZWA", "OH2ZWD", "OH2ZWE"]);
  });

  it("closes the oldest card of a row that is too wide that is not pinned, never the newest", () => {
    const { picked } = setUp();
    for (const call of CALLS.slice(0, 3)) picked.pick(call, true);
    picked.pin("OH2ZWA", true);
    picked.closeOldest();
    expect(picked.open.value).toEqual(["OH2ZWA", "OH2ZWC"]);
    picked.closeOldest();
    expect(picked.open.value).toEqual(["OH2ZWA", "OH2ZWC"]);
  });

  it("opens the pinned cards that came back with the page when the daemon has told the stations, and lets go of one it does not have", async () => {
    const { stations, ready, pins, picked } = setUp(4, ["OH2ZWB", "OH2ZWX", "OH2ZWA"], false);
    stations.value = new Map();
    await nextTick();
    expect([picked.open.value, pins.value]).toEqual([[], ["OH2ZWB", "OH2ZWX", "OH2ZWA"]]);
    stations.value = all();
    ready.value = true;
    await nextTick();
    expect(picked.open.value).toEqual(["OH2ZWB", "OH2ZWA"]);
    expect(pins.value).toEqual(["OH2ZWB", "OH2ZWA"]);
    expect(picked.selected.value).toBe("OH2ZWA");
  });

  it("lets go of a pinned card whose station is forgotten later", async () => {
    const { stations, pins, picked } = setUp(4, ["OH2ZWA"]);
    await nextTick();
    expect(picked.open.value).toEqual(["OH2ZWA"]);
    stations.value = new Map([["OH2ZWB", station("OH2ZWB")]]);
    await nextTick();
    expect([picked.open.value, pins.value]).toEqual([[], []]);
  });

  it("ignores the pins where they are off (a phone) and brings the cards back when they are on again", async () => {
    const { pinsOn, picked } = setUp(1, ["OH2ZWA"]);
    await nextTick();
    pinsOn.value = false;
    await nextTick();
    picked.pick("OH2ZWB");
    expect(picked.open.value).toEqual(["OH2ZWB"]);
    expect(picked.closeAll()).toBe(true);
    pinsOn.value = true;
    await nextTick();
    expect(picked.open.value).toEqual(["OH2ZWA"]);
  });
});
