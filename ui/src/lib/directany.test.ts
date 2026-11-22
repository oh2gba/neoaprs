// The check mark after a call, the map ring and the "direct only" filter count a station heard
// direct on any radio, HF too. They read `last_direct_any_at`, and fall back to `last_direct_at`
// (radios that may carry a path) only if the daemon does not give it. The reach circle, Nearby's
// direct list and the farthest direct still use `last_direct_at`.
import { describe, expect, it } from "vitest";
import { heardDirect, heardDirectRecently } from "@/lib/routes";
import { directAt, listStations } from "@/lib/stations";
import type { StationRow } from "@/protocol/protocol";
import { NOW, ago, heardBy, station } from "@/test/fixtures";

/** Heard on the HF radio alone: every HF frame is direct, and HF carries no path. */
const hfDirect = station("OH2HF", {
  heard_rf: 2,
  heard: heardBy([2, 2, ago(120)]),
  last_direct_at: null,
  last_direct_any_at: ago(120),
  heard_direct: 0,
});
const fmDirect = station("OH2FM", { last_direct_at: ago(300), last_direct_any_at: ago(300), heard_direct: 2 });
const never = station("OH2VIA", { last_direct_at: null, last_direct_any_at: null });

describe("a station heard direct on any radio", () => {
  it("has its time from any radio, else, against a daemon that does not give it, from the radios that may carry a path", () => {
    expect([directAt(hfDirect), directAt(fmDirect), directAt(never)]).toEqual([ago(120), ago(300), null]);
    const before: Partial<StationRow> = { ...fmDirect };
    delete before.last_direct_any_at;
    expect(directAt(before as StationRow)).toBe(ago(300));
  });

  it("has the check mark after its call, a Mercury station too", () => {
    expect([hfDirect, fmDirect, never].map(heardDirect)).toEqual([true, true, false]);
    expect(heardDirect({ ...hfDirect, is_me: true })).toBe(false);
  });

  it("has the map's ring while it was heard direct within the hour, on any radio", () => {
    expect([hfDirect, fmDirect, never].map((row) => heardDirectRecently(row, NOW))).toEqual([true, true, false]);
    expect(heardDirectRecently({ ...hfDirect, last_direct_any_at: ago(7200) }, NOW)).toBe(false);
  });

  it("is kept by the filter direct only, a Mercury station too", () => {
    const kept = listStations([hfDirect, fmDirect, never], {
      filter: "",
      directOnly: true,
      sort: { key: "call", dir: 1 },
    });
    expect(kept.map((row) => row.call)).toEqual(["OH2FM", "OH2HF"]);
  });
});
