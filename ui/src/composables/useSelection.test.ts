import { describe, expect, it, vi } from "vitest";
import { nextTick, shallowRef } from "vue";
import { useSelection } from "@/composables/useSelection";
import type { Command, StationRow } from "@/protocol/protocol";
import { station } from "@/test/fixtures";

function setUp(taken = true) {
  const stations = shallowRef<ReadonlyMap<string, StationRow>>(new Map([["OH2RDG", station("OH2RDG")]]));
  const send = vi.fn((_command: Command) => taken);
  return { stations, send, picked: useSelection(stations, send) };
}

describe("useSelection", () => {
  it("flies the map to a station picked in the table, again for the same one picked twice", () => {
    const { picked } = setUp();
    picked.pickFromTable("OH2RDG");
    expect([picked.selected.value, picked.focus.value]).toEqual(["OH2RDG", { call: "OH2RDG", n: 1 }]);
    expect(picked.row.value?.call).toBe("OH2RDG");
    picked.pickFromTable("OH2RDG");
    expect(picked.focus.value).toEqual({ call: "OH2RDG", n: 2 });
  });

  it("lets go of a station the daemon no longer has", async () => {
    const { stations, picked } = setUp();
    picked.selected.value = "OH2RDG";
    await nextTick();
    stations.value = new Map();
    await nextTick();
    expect([picked.selected.value, picked.row.value]).toEqual([null, null]);
  });

  it("forgets a station through the daemon, and lets go of it only when the command went out", () => {
    const { send, picked } = setUp();
    picked.selected.value = "OH2RDG";
    picked.forget("OH2RDG");
    expect(send).toHaveBeenCalledWith({ cmd: "forget_station", call: "OH2RDG" });
    expect(picked.selected.value).toBeNull();
    const offline = setUp(false).picked;
    offline.selected.value = "OH2RDG";
    offline.forget("OH2RDG");
    expect(offline.selected.value).toBe("OH2RDG");
  });
});
