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
  it("splits what the daemon tells into the paths, the timeouts, the attempts and the stations that are RF only, leaving out what is null", () => {
    const { prefs, own } = setUp();
    prefs.set("OH2RDG", { path: "WIDE2-1", hide_after_min: null, attempts: null, rf_only: false });
    prefs.set("OH2XYZ", { path: "", hide_after_min: 0, attempts: null, rf_only: true });
    prefs.set("OH2PU-9", { path: null, hide_after_min: 90, attempts: 2, rf_only: false });
    expect([...own.paths.value]).toEqual([
      ["OH2RDG", "WIDE2-1"],
      ["OH2XYZ", ""],
    ]);
    expect([...own.timeouts.value]).toEqual([
      ["OH2XYZ", 0],
      ["OH2PU-9", 90],
    ]);
    expect([...own.attempts.value]).toEqual([["OH2PU-9", 2]]);
    expect([...own.rfOnly.value]).toEqual(["OH2XYZ"]);
  });

  it("follows a change", () => {
    const { prefs, own } = setUp();
    expect(own.timeouts.value.size).toBe(0);
    prefs.set("A", { path: null, hide_after_min: 5, attempts: null, rf_only: false });
    expect(own.timeouts.value.get("A")).toBe(5);
    prefs.delete("A");
    expect(own.timeouts.value.size).toBe(0);
    prefs.set("B", { path: null, hide_after_min: null, attempts: null, rf_only: true });
    expect(own.rfOnly.value.has("B")).toBe(true);
    prefs.set("B", { path: "WIDE2-1", hide_after_min: null, attempts: null, rf_only: false });
    expect(own.rfOnly.value.has("B")).toBe(false);
  });

  it("sends the seven commands", () => {
    const { send, own } = setUp();
    own.setPath("A", "WIDE1-1");
    own.clearPath("A");
    own.setTimeoutMin("A", 0);
    own.clearTimeoutMin("A");
    own.setAttempts("A", 2);
    own.clearAttempts("A");
    own.setRfOnly("A", true);
    own.setRfOnly("A", false);
    expect(send.mock.calls.map((c) => c[0])).toEqual([
      { cmd: "set_station_path", call: "A", path: "WIDE1-1" },
      { cmd: "clear_station_path", call: "A" },
      { cmd: "set_station_timeout", call: "A", minutes: 0 },
      { cmd: "clear_station_timeout", call: "A" },
      { cmd: "set_station_attempts", call: "A", attempts: 2 },
      { cmd: "clear_station_attempts", call: "A" },
      { cmd: "set_station_rf_only", call: "A", on: true },
      { cmd: "set_station_rf_only", call: "A", on: false },
    ]);
  });
});
