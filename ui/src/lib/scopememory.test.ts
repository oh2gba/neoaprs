// What the page keeps of the HF radio's waterfall (lib/scopememory.ts): the rows as they come, each at its moment, for two minutes; the rows the daemon kept, which fill the time nobody looked without doubling a row or moving
// one held, and are all of it where they do not go on from what is held; the stations heard, placed by the daemon's clock; a computer clock set back; and what the listeners are told.
import { describe, expect, it } from "vitest";
import { ScopeMemory, type KeptRow } from "@/lib/scopememory";
import type { AgedRow, ScopeHistory, ScopeRow } from "@/lib/scoperow";
import { BINS } from "@/lib/waterfall";
import { LIMITS } from "@/protocol/lists";

const START = Date.UTC(2026, 10, 14, 12, 0, 0);
/** A row the daemon could send, told apart by `n` (its first bin) and by its level. */
const row = (n: number, tx = false): ScopeRow => {
  const db = new Float32Array(BINS).fill(-50);
  db[0] = -100 + n;
  return { db, level: -40 - (n % 7), tx };
};
const first = (kept: readonly KeptRow[]): number[] => kept.map((k) => k.row.db[0] + 100);

function memory() {
  const clock = { now: START };
  const kept = new ScopeMemory(() => clock.now);
  const told: string[] = [];
  kept.listen({ row: (k) => told.push(`row ${k.row.db[0] + 100}`), heard: (h) => told.push(`heard ${h.call}`), whole: () => told.push("whole") });
  /** Rows as they come, one every 120 ms from now on. */
  const live = (...ns: number[]): void => {
    for (const n of ns) {
      kept.live(row(n));
      clock.now += 120;
    }
  };
  return { clock, kept, told, live };
}

/** The daemon's rows kept, as at the moment `now`: the row `n` made at `made(n)`. */
const aged = (ns: number[], made: (n: number) => number, now: number): AgedRow[] => ns.map((n) => ({ row: row(n), age: now - made(n) }));
/** The rows kept as the daemon sends them, its clock `ahead` of this page's at `now`. */
const sent = (rows: AgedRow[], now: number, ahead = 0): ScopeHistory => ({ rows, clock: now + ahead });

describe("what the page keeps of the waterfall", () => {
  it("keeps each row at the moment it came, as the floor tells it, for two minutes and no longer", () => {
    const { clock, kept, told, live } = memory();
    live(1, 2, 3);
    expect(first(kept.rows)).toEqual([1, 2, 3]);
    expect(kept.rows.map((k) => k.at)).toEqual([START, START + 120, START + 240]);
    expect(kept.rows[0].bytes).toHaveLength(BINS);
    expect(told).toEqual(["row 1", "row 2", "row 3"]);
    clock.now = START + LIMITS.scope.historySec * 1000 + 200;
    live(4);
    expect(first(kept.rows)).toEqual([3, 4]); // (what is older than two minutes is let go)
  });

  it("takes the rows the daemon kept as all of it when it holds none, each at the moment its age says, oldest first", () => {
    const { clock, kept, told } = memory();
    clock.now = START + 60_000;
    kept.history(
      sent(
        aged([1, 2, 3], (n) => START + n * 1000, clock.now),
        clock.now,
      ),
    );
    expect(first(kept.rows)).toEqual([1, 2, 3]);
    expect(kept.rows.map((k) => k.at)).toEqual([START + 1000, START + 2000, START + 3000]);
    expect(told).toEqual(["whole"]);
  });

  it("fills the time nobody looked with the rows the daemon kept that are newer than the newest it holds: none twice, and the rows held stay as they were", () => {
    const { clock, kept, live } = memory();
    live(1, 2, 3, 4); // (live at 0, 120, 240 and 360 ms)
    const held = [...kept.rows];
    clock.now = START + 30_000; // (half a minute on another tab)
    const made = (n: number): number => START + (n - 1) * 120 + 15; // (the daemon made each 15 ms before it came here)
    kept.history(sent(aged([1, 2, 3, 4, 5, 6, 7], made, clock.now), clock.now));
    expect(first(kept.rows)).toEqual([1, 2, 3, 4, 5, 6, 7]);
    expect(kept.rows.slice(0, 4)).toEqual(held); // (the same rows, the same moments, the same bytes)
    expect(kept.rows.slice(4).map((k) => k.at)).toEqual([made(5), made(6), made(7)]);
    clock.now += 100;
    live(8);
    expect(first(kept.rows)).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
  });

  it("finds the newest row it holds among the daemon's by the row before it too, where two rows are the same", () => {
    const { clock, kept } = memory();
    kept.live(row(1));
    clock.now += 120;
    kept.live(row(9));
    clock.now += 120;
    kept.live(row(9));
    clock.now = START + 2000;
    const rows = [1, 9, 9, 9].map((n, i) => ({ row: row(n), age: clock.now - (START + i * 120) }));
    kept.history(sent(rows, clock.now));
    expect(first(kept.rows)).toEqual([1, 9, 9, 9]);
  });

  it("takes the daemon's rows as all of it where they do not go on from what it holds: the daemon forgot, or kept less, or kept more before", () => {
    const { clock, kept, live } = memory();
    live(1, 2, 3);
    clock.now = START + 10_000;
    kept.history(
      sent(
        aged([20, 21], (n) => START + n * 400, clock.now),
        clock.now,
      ),
    ); // (the modem was started anew: the daemon has none of these)
    expect(first(kept.rows)).toEqual([20, 21]);
    kept.history(sent([], clock.now)); // (the daemon forgot what it kept)
    expect(kept.rows).toEqual([]);
    live(1, 2);
    clock.now = START + 60_000;
    kept.history(
      sent(
        aged([30, 1, 2, 3], (n) => (n === 30 ? START - 5000 : START + 10_000 + (n - 1) * 120), clock.now),
        clock.now,
      ),
    ); // (it kept a row from before the first held)
    expect(first(kept.rows)).toEqual([30, 1, 2, 3]);
  });

  it("writes down the stations heard in the time kept, in the order of their moments, and tells the listeners: one heard just now at this moment with the SNR, one told later at its time with the call alone", () => {
    const { clock, kept, told } = memory();
    clock.now = START + 200_000;
    kept.hear("OH2NEW", -3, START + 199_000); // (the daemon writes whole seconds, and the packet took a tick to come)
    kept.hear("OH2OLD", -3, START + 190_000); // (told ten seconds late: the SNR now is of another frame)
    kept.hear("OH2GONE", null, START);
    expect(kept.heard.map(({ at, call, snr }) => ({ at, call, snr }))).toEqual([
      { at: START + 190_500, call: "OH2OLD", snr: null },
      { at: START + 200_000, call: "OH2NEW", snr: -3 },
    ]);
    expect(told).toEqual(["heard OH2NEW", "heard OH2OLD"]);
  });

  it("places the stations told late by the daemon's clock, and again when the rows kept say it better: a reconnect after a drop, a computer whose clock is behind", () => {
    const { clock, kept } = memory();
    clock.now = START + 60_000;
    const ahead = 40_000; // (the station's clock is 40 s ahead of this computer's)
    kept.hear("OH2EARLY", -3, START + 60_000 + ahead - 15_000); // (before the page knows the daemon's clock: taken to agree, so it is in the future, and no SNR is taken for it)
    kept.history(
      sent(
        aged([1, 2], (n) => START + 50_000 + n * 120, clock.now),
        clock.now,
        ahead,
      ),
    );
    expect(kept.heard.map(({ at, snr }) => [at, snr])).toEqual([[START + 45_500, null]]); // (fifteen seconds before now, by this page's clock)
    clock.now += 20_000; // (the Wi-Fi away for 20 s; two stations heard meanwhile are told on the return)
    kept.hear("OH2FIVE", -3, START + 80_000 + ahead - 5_000);
    kept.hear("OH2FIFTEEN", -3, START + 80_000 + ahead - 15_000);
    kept.hear("OH2NOW", -7, START + 80_000 + ahead);
    expect(kept.heard.map(({ at, call, snr }) => [call, at - clock.now, snr])).toEqual([
      ["OH2EARLY", -34_500, null],
      ["OH2FIFTEEN", -14_500, null],
      ["OH2FIVE", -4_500, null],
      ["OH2NOW", 0, -7],
    ]);
  });

  it("goes on forward when the computer's clock is set back: each row as long after the one before as passed", () => {
    const clock = { now: START, steady: 0 };
    const kept = new ScopeMemory(
      () => clock.now,
      () => clock.steady,
    );
    for (let i = 0; i < 3; i++) {
      kept.live(row(i));
      clock.now += 120;
      clock.steady += 120;
    }
    clock.now -= 30_000; // (a time sync puts a fast clock right)
    for (let i = 3; i < 6; i++) {
      kept.live(row(i));
      clock.now += 120;
      clock.steady += 120;
    }
    expect(kept.rows.map((k) => k.at - START)).toEqual([0, 120, 240, 360, 480, 600]);
    expect(kept.now() - START).toBe(720);
  });

  it("stops telling a listener that stopped", () => {
    const { kept, told, live } = memory();
    const other: string[] = [];
    const stop = kept.listen({ row: () => other.push("row") });
    live(1);
    stop();
    live(2);
    expect(other).toEqual(["row"]);
    expect(told).toEqual(["row 1", "row 2"]);
  });
});
