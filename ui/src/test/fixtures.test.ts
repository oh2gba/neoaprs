// The makers of rows give the fields of the radios as the daemon sends them for a station with FM radio 1 and HF radio 2 (tests/fixtures/wire/rows.json holds the daemon's own rows), so that a test that reads them
// does not pass on a row the daemon never sends.
import { describe, expect, it } from "vitest";
import { message, ownObject, station } from "@/test/fixtures";

describe("the makers of rows", () => {
  it("give a station heard on HF alone its HF time as the time last heard direct on any radio, as the daemon's row of Q3TKU has it", () => {
    const q3tku = station("Q3TKU", {
      heard_rf: 1,
      heard_fm: 0,
      heard_hf: 1,
      last_fm_at: null,
      last_hf_at: "2026-10-21T12:00:00Z",
      last_direct_at: null,
      heard_direct: 0,
    });
    expect([q3tku.last_direct_any_at, q3tku.heard, q3tku.last_path_radio]).toEqual([
      "2026-10-21T12:00:00Z",
      { "2": { count: 1, last_at: "2026-10-21T12:00:00Z" } },
      2,
    ]);
    const both = station("OH2BOTH", { heard_fm: 2, heard_hf: 1, last_direct_at: "2026-10-21T11:00:00Z", last_hf_at: "2026-10-21T11:30:00Z" });
    expect(both.last_direct_any_at).toBe("2026-10-21T11:30:00Z");
    const fm = station("OH2FM", { heard_fm: 2, heard_hf: 0, last_direct_at: "2026-10-21T11:00:00Z" });
    expect(fm.last_direct_any_at).toBe("2026-10-21T11:00:00Z");
    expect(station("OH2DIGI", { heard_fm: 2, heard_hf: 0, last_direct_at: null }).last_direct_any_at).toBeNull();
  });

  it("give a message of ours on its way that went on a radio that radio for its next attempt, and none to one that is not on its way", () => {
    expect([
      message(1, { state: "sending", radio: "hf" }).radio_now,
      message(2, { state: "queued", radio: "fm" }).radio_now,
      message(3, { state: "acked", radio: "hf" }).radio_now,
      message(4, { direction: "in", state: "received", radio: "hf" }).radio_now,
      message(5, { state: "sending", radio: "hf", radio_now: 1 }).radio_now,
    ]).toEqual([2, 1, null, null, 1]);
  });

  it("give an object the radios of its word with both radios on, and those a test gives", () => {
    expect([ownObject("A").radios, ownObject("B", { radio: "both" }).radios, ownObject("C", { radio: "both", radios: [1] }).radios]).toEqual([
      [1],
      [1, 2],
      [1],
    ]);
  });
});
