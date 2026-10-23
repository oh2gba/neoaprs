import { describe, expect, it, vi } from "vitest";
import { nextTick, ref, shallowRef } from "vue";
import { useSelection } from "@/composables/useSelection";
import type { Command, StationRow } from "@/protocol/protocol";
import { station } from "@/test/fixtures";

const CALLS = ["OH2ZWA", "OH2ZWB", "OH2ZWC", "OH2ZWD", "OH2ZWE", "OH2ZWF", "OH2ZWG"];

function setUp(capacity = 4) {
  const stations = shallowRef<ReadonlyMap<string, StationRow>>(new Map(CALLS.map((call) => [call, station(call)] as const)));
  const room = ref(capacity);
  const send = vi.fn((_command: Command) => true);
  return { stations, room, send, picked: useSelection(stations, send, room) };
}

describe("useSelection with several cards", () => {
  it("opens one card at a time for a plain click: the new one replaces the open ones", () => {
    const { picked } = setUp();
    picked.pick("OH2ZWA");
    picked.pick("OH2ZWB");
    expect(picked.open.value).toEqual(["OH2ZWB"]);
    expect(picked.others.value).toEqual([]);
  });

  it("adds the card with Ctrl (Cmd) held, the newest being the selected one, and closes it when it is open already", () => {
    const { picked } = setUp();
    picked.pick("OH2ZWA");
    expect(picked.pick("OH2ZWB", true)).toBe(true);
    picked.pick("OH2ZWC", true);
    expect(picked.open.value).toEqual(["OH2ZWA", "OH2ZWB", "OH2ZWC"]);
    expect([picked.selected.value, picked.others.value]).toEqual(["OH2ZWC", ["OH2ZWA", "OH2ZWB"]]);
    expect(picked.rows.value.map((row) => row.call)).toEqual(["OH2ZWA", "OH2ZWB", "OH2ZWC"]);
    expect(picked.pick("OH2ZWB", true)).toBe(false);
    expect(picked.open.value).toEqual(["OH2ZWA", "OH2ZWC"]);
    picked.pick("OH2ZWC", true);
    expect(picked.selected.value).toBe("OH2ZWA");
  });

  it("closes the oldest card when a new one would be over the capacity", () => {
    const { picked } = setUp(3);
    for (const call of CALLS.slice(0, 5)) picked.pick(call, true);
    expect(picked.open.value).toEqual(["OH2ZWC", "OH2ZWD", "OH2ZWE"]);
  });

  it("has the capacity of the size: one on a phone, where Ctrl does not exist and a tap replaces the card", () => {
    const { picked } = setUp(1);
    picked.pick("OH2ZWA", true);
    picked.pick("OH2ZWB", true);
    expect(picked.open.value).toEqual(["OH2ZWB"]);
    expect(picked.pick("OH2ZWB", true)).toBe(true); // (not toggled away: there is nothing to add it to)
    expect(picked.open.value).toEqual(["OH2ZWB"]);
  });

  it("closes the oldest cards when the room gets smaller (a window made lower, a tablet turned)", async () => {
    const { picked, room } = setUp(5);
    for (const call of CALLS.slice(0, 4)) picked.pick(call, true);
    room.value = 2;
    await nextTick();
    expect(picked.open.value).toEqual(["OH2ZWC", "OH2ZWD"]);
    room.value = 0; // (never fewer than one)
    await nextTick();
    expect(picked.open.value).toEqual(["OH2ZWD"]);
  });

  it("closes one card, or all of them at once (Esc), clearing the selection, and says whether there was one", () => {
    const { picked } = setUp();
    for (const call of CALLS.slice(0, 3)) picked.pick(call, true);
    picked.close("OH2ZWB");
    expect(picked.open.value).toEqual(["OH2ZWA", "OH2ZWC"]);
    picked.pick("OH2ZWB", true);
    expect(picked.closeAll()).toBe(true);
    expect([picked.open.value, picked.selected.value, picked.others.value]).toEqual([[], null, []]);
    expect(picked.closeAll()).toBe(false);
  });

  it("closes the oldest card when the row does not fit, but never the only one", () => {
    const { picked } = setUp();
    for (const call of CALLS.slice(0, 3)) picked.pick(call, true);
    picked.closeOldest();
    expect(picked.open.value).toEqual(["OH2ZWB", "OH2ZWC"]);
    picked.closeOldest();
    picked.closeOldest();
    expect(picked.open.value).toEqual(["OH2ZWC"]);
  });

  it("flies the map to a station picked in the table, and not to one that is added to the others or closed", () => {
    const { picked } = setUp();
    picked.pickFromTable("OH2ZWA");
    expect(picked.focus.value).toEqual({ call: "OH2ZWA", n: 1 });
    picked.pickFromTable("OH2ZWB", true);
    expect(picked.focus.value).toEqual({ call: "OH2ZWA", n: 1 });
    expect(picked.open.value).toEqual(["OH2ZWA", "OH2ZWB"]);
    picked.pickFromTable("OH2ZWB", true);
    expect(picked.open.value).toEqual(["OH2ZWA"]);
    picked.pickFromTable("OH2ZWC");
    expect(picked.focus.value).toEqual({ call: "OH2ZWC", n: 2 });
    expect(picked.open.value).toEqual(["OH2ZWC"]);
  });

  it("lets go of a station the daemon has forgotten, and keeps the other cards", async () => {
    const { stations, picked } = setUp();
    for (const call of CALLS.slice(0, 3)) picked.pick(call, true);
    stations.value = new Map([...stations.value].filter(([call]) => call !== "OH2ZWB"));
    await nextTick();
    expect(picked.open.value).toEqual(["OH2ZWA", "OH2ZWC"]);
  });

  it("forgets a station through the daemon and closes only its card", () => {
    const { picked, send } = setUp();
    for (const call of CALLS.slice(0, 2)) picked.pick(call, true);
    picked.forget("OH2ZWA");
    expect(send).toHaveBeenCalledWith({ cmd: "forget_station", call: "OH2ZWA" });
    expect(picked.open.value).toEqual(["OH2ZWB"]);
  });

  it("is made the only card by assigning its call, and cleared by assigning null", () => {
    const { picked } = setUp();
    for (const call of CALLS.slice(0, 3)) picked.pick(call, true);
    picked.selected.value = "OH2ZWB";
    expect(picked.open.value).toEqual(["OH2ZWB"]);
    picked.selected.value = null;
    expect(picked.open.value).toEqual([]);
  });
});
