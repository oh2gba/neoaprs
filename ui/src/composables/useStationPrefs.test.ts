import { describe, expect, it, vi } from "vitest";
import { shallowReactive } from "vue";
import { useStationPrefs } from "@/composables/useStationPrefs";
import type { Command, StationPref } from "@/protocol/protocol";

function setUp() {
  const prefs = shallowReactive(new Map<string, StationPref>());
  const send = vi.fn((_command: Command) => true);
  return { prefs, send, own: useStationPrefs(prefs, send) };
}

describe("useStationPrefs", () => {
  it("splits what the daemon tells into the paths and the stations that are RF only, leaving out what is null", () => {
    const { prefs, own } = setUp();
    prefs.set("OH2RDG", { path: "WIDE2-1", rf_only: false });
    prefs.set("OH2XYZ", { path: "", rf_only: true });
    prefs.set("OH2PU-9", { path: null, rf_only: false });
    expect([...own.paths.value]).toEqual([
      ["OH2RDG", "WIDE2-1"],
      ["OH2XYZ", ""],
    ]);
    expect([...own.rfOnly.value]).toEqual(["OH2XYZ"]);
  });

  it("follows a change", () => {
    const { prefs, own } = setUp();
    expect(own.paths.value.size).toBe(0);
    prefs.set("A", { path: "WIDE1-1", rf_only: false });
    expect(own.paths.value.get("A")).toBe("WIDE1-1");
    prefs.delete("A");
    expect(own.paths.value.size).toBe(0);
    prefs.set("B", { path: null, rf_only: true });
    expect(own.rfOnly.value.has("B")).toBe(true);
    prefs.set("B", { path: "WIDE2-1", rf_only: false });
    expect(own.rfOnly.value.has("B")).toBe(false);
  });

  it("sends the four commands", () => {
    const { send, own } = setUp();
    own.setPath("A", "WIDE1-1");
    own.clearPath("A");
    own.setRfOnly("A", true);
    own.setRfOnly("A", false);
    expect(send.mock.calls.map((c) => c[0])).toEqual([
      { cmd: "set_station_path", call: "A", path: "WIDE1-1" },
      { cmd: "clear_station_path", call: "A" },
      { cmd: "set_station_rf_only", call: "A", on: true },
      { cmd: "set_station_rf_only", call: "A", on: false },
    ]);
  });
});
