import { describe, expect, it, vi } from "vitest";
import { ref, shallowRef } from "vue";
import { useSelection } from "@/composables/useSelection";
import { MOST_OPEN } from "@/lib/cardmove";
import type { StationRow } from "@/protocol/protocol";
import { station } from "@/test/fixtures";

const CALLS = ["OH2ZWA", "OH2ZWB", "OH2ZWC", "OH2ZWD", "OH2ZWE"];

function setUp(capacity: number, moved: string[], calls: string[] = CALLS) {
  const stations = shallowRef<ReadonlyMap<string, StationRow>>(new Map(calls.map((call) => [call, station(call)] as const)));
  const away = ref(moved);
  return { away, picked: useSelection(stations, vi.fn(() => true), ref(capacity), () => away.value) };
}

describe("useSelection with cards the user has moved out of the row", () => {
  it("counts only the cards in the row against the capacity: a moved card stays open when the row is full, and the oldest card in the row closes", () => {
    const { away, picked } = setUp(2, []);
    picked.pick("OH2ZWA");
    picked.pick("OH2ZWB", true);
    away.value = ["OH2ZWA"];
    picked.pick("OH2ZWC", true);
    expect(picked.open.value).toEqual(["OH2ZWA", "OH2ZWB", "OH2ZWC"]);
    picked.pick("OH2ZWD", true);
    expect(picked.open.value).toEqual(["OH2ZWA", "OH2ZWC", "OH2ZWD"]);
  });

  it("closes the oldest card of a row that is too wide, never a moved one, and never the only one in the row", () => {
    const { picked } = setUp(4, ["OH2ZWA"]);
    for (const call of CALLS.slice(0, 3)) picked.pick(call, true);
    picked.closeOldest();
    expect(picked.open.value).toEqual(["OH2ZWA", "OH2ZWC"]);
    picked.closeOldest();
    expect(picked.open.value).toEqual(["OH2ZWA", "OH2ZWC"]);
  });

  it("keeps at most MOST_OPEN cards open in all, however many are moved: the oldest closes", () => {
    const many = Array.from({ length: MOST_OPEN + 2 }, (_, i) => `OH2Z${i}`);
    const { picked } = setUp(2, many, many);
    for (const call of many) picked.pick(call, true);
    expect(picked.open.value).toEqual(many.slice(2));
  });

  it("closes the oldest cards of the row when the window gets smaller, but not the moved ones", async () => {
    const stations = shallowRef<ReadonlyMap<string, StationRow>>(new Map(CALLS.map((call) => [call, station(call)] as const)));
    const room = ref(4);
    const picked = useSelection(stations, vi.fn(() => true), room, () => ["OH2ZWA"]);
    for (const call of CALLS.slice(0, 4)) picked.pick(call, true);
    room.value = 2;
    await Promise.resolve();
    expect(picked.open.value).toEqual(["OH2ZWA", "OH2ZWC", "OH2ZWD"]);
  });

  it("a plain click replaces every card, the moved ones too", () => {
    const { picked } = setUp(4, ["OH2ZWA"]);
    picked.pick("OH2ZWA");
    picked.pick("OH2ZWB", true);
    picked.pick("OH2ZWC");
    expect(picked.open.value).toEqual(["OH2ZWC"]);
  });
});
