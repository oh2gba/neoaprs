// The check mark after a call, the ring of the map and the filter "direct only" count a station heard direct on ANY radio, HF too (plan 6b; i3/final.md section 5): they read the time the daemon gives for any radio
// (`last_direct_any_at`), and the time of the radios that may carry a path (`last_direct_at`) only against a daemon that does not give it. The reach circle, Nearby's direct list and the farthest direct stay the path
// radios' (`last_direct_at`).
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
    const kept = listStations([hfDirect, fmDirect, never], { filter: "", directOnly: true, sort: { key: "call", dir: 1 } });
    expect(kept.map((row) => row.call)).toEqual(["OH2FM", "OH2HF"]);
  });
});
