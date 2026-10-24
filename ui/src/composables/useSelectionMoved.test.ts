import { describe, expect, it, vi } from "vitest";
import { ref, shallowRef } from "vue";
import { useSelection } from "@/composables/useSelection";
import type { StationRow } from "@/protocol/protocol";
import { station } from "@/test/fixtures";

const CALLS = ["OH2ZWA", "OH2ZWB", "OH2ZWC", "OH2ZWD", "OH2ZWE"];

function setUp(capacity: number) {
  const stations = shallowRef<ReadonlyMap<string, StationRow>>(new Map(CALLS.map((call) => [call, station(call)] as const)));
  const room = ref(capacity);
  return {
    room,
    picked: useSelection(
      stations,
      vi.fn(() => true),
      room,
    ),
  };
}

// (a card the user has moved leaves its slot empty and stands where it is put: as far as how many may be open goes it is a card like the others)
describe("useSelection counts every open card against the capacity", () => {
  it("closes the oldest card when a new one would be one too many, wherever the cards stand", () => {
    const { picked } = setUp(2);
    picked.pick("OH2ZWA");
    picked.pick("OH2ZWB", true);
    picked.pick("OH2ZWC", true);
    expect(picked.open.value).toEqual(["OH2ZWB", "OH2ZWC"]);
  });

  it("closes the oldest card of a row that is too wide, never the only one", () => {
    const { picked } = setUp(4);
    for (const call of CALLS.slice(0, 3)) picked.pick(call, true);
    picked.closeOldest();
    expect(picked.open.value).toEqual(["OH2ZWB", "OH2ZWC"]);
    picked.closeOldest();
    picked.closeOldest();
    expect(picked.open.value).toEqual(["OH2ZWC"]);
  });

  it("closes the oldest cards when the window gets smaller", async () => {
    const { room, picked } = setUp(4);
    for (const call of CALLS.slice(0, 4)) picked.pick(call, true);
    room.value = 2;
    await Promise.resolve();
    expect(picked.open.value).toEqual(["OH2ZWC", "OH2ZWD"]);
  });
});
