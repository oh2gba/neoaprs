import { describe, expect, it } from "vitest";
import { LIMITS } from "@/protocol/lists";
import { HISTORY_KIND, ROW_KIND, dbOfRowByte, parseScopeFrame, parseScopeHistory, parseScopeRow } from "@/lib/scoperow";

const { rowBins } = LIMITS.scope;

/** A frame as neoaprs/mercuryscope.py `row_frame` makes it. */
function frame(flags: number, level: number, bins: Uint8Array = new Uint8Array(rowBins)): ArrayBuffer {
  const bytes = new Uint8Array(3 + bins.length);
  bytes.set([ROW_KIND, flags, level & 0xff], 0);
  bytes.set(bins, 3);
  return bytes.buffer;
}

describe("a row of the waterfall", () => {
  it("is the passband's bins in the modem's dB, a byte half a dB from minus 110", () => {
    expect(rowBins).toBe(307);
    expect([0, 1, 220, 255].map(dbOfRowByte)).toEqual([-110, -109.5, 0, 17.5]);
    const bins = new Uint8Array(rowBins);
    bins[0] = 220;
    bins[306] = 255;
    const row = parseScopeRow(frame(0, -41, bins));
    expect(row).not.toBeNull();
    expect(row?.db).toHaveLength(307);
    expect([row?.db[0], row?.db[1], row?.db[306]]).toEqual([0, -110, 17.5]);
  });

  it("says the level as a signed byte and the transmission as the first flag", () => {
    expect(parseScopeRow(frame(0, -41))).toMatchObject({ level: -41, tx: false });
    expect(parseScopeRow(frame(1, -90))).toMatchObject({ level: -90, tx: true });
    expect(parseScopeRow(frame(0, 0))).toMatchObject({ level: 0, tx: false });
    expect(parseScopeRow(frame(0xfe, -3))?.tx).toBe(false);
  });

  it("is null for a frame of another kind or another size", () => {
    const other = new Uint8Array(frame(0, 0));
    other[0] = 2;
    expect(parseScopeRow(other.buffer)).toBeNull();
    expect(parseScopeRow(new ArrayBuffer(0))).toBeNull();
    expect(parseScopeRow(frame(0, 0, new Uint8Array(rowBins - 1)))).toBeNull();
    expect(parseScopeRow(frame(0, 0, new Uint8Array(rowBins + 1)))).toBeNull();
  });
});

const CLOCK = Date.UTC(2026, 10, 14, 12, 0, 0) + 0.25;

/** A frame of the rows kept as neoaprs/mercuryscope.py `history_frame` makes it: the kind and the daemon's clock (a little-endian float64), then each row its flags, its level, its age (four bytes, little-endian) and its bins. */
function history(rows: { flags: number; level: number; age: number; bin: number }[]): ArrayBuffer {
  const size = 6 + rowBins;
  const bytes = new Uint8Array(9 + rows.length * size);
  bytes[0] = HISTORY_KIND;
  new DataView(bytes.buffer).setFloat64(1, CLOCK, true);
  rows.forEach((row, i) => {
    const at = 9 + i * size;
    bytes.set([row.flags, row.level & 0xff], at);
    new DataView(bytes.buffer).setUint32(at + 2, row.age, true);
    bytes.fill(row.bin, at + 6, at + size);
  });
  return bytes.buffer;
}

describe("the rows the daemon kept", () => {
  it("are each row with its age in milliseconds, oldest first, and none is a frame that says to forget", () => {
    const kept = parseScopeHistory(
      history([
        { flags: 0, level: -41, age: 119_950, bin: 100 },
        { flags: 1, level: -12, age: 120, bin: 220 },
      ]),
    );
    expect(kept?.clock).toBe(CLOCK);
    expect(kept?.rows.map(({ row, age }) => [age, row.level, row.tx, row.db[0], row.db[306], row.db.length])).toEqual([
      [119_950, -41, false, -60, -60, 307],
      [120, -12, true, 0, 0, 307],
    ]);
    expect(parseScopeHistory(history([]))).toEqual({ rows: [], clock: CLOCK });
    expect(parseScopeHistory(Uint8Array.of(HISTORY_KIND).buffer)).toBeNull(); // (the kind without the clock)
  });

  it("are null for a frame that is not a whole number of them, or of another kind", () => {
    const whole = new Uint8Array(history([{ flags: 0, level: -41, age: 5, bin: 1 }]));
    expect(parseScopeHistory(whole.subarray(0, whole.length - 1).slice().buffer)).toBeNull();
    expect(parseScopeHistory(frame(0, -41))).toBeNull();
    whole[0] = 3;
    expect(parseScopeHistory(whole.buffer)).toBeNull();
    expect(parseScopeHistory(new ArrayBuffer(0))).toBeNull();
  });
});

describe("a binary frame", () => {
  it("is a row, the rows kept, or nothing this page knows: a kind it does not know is let go, as a page of the version before lets the rows kept go", () => {
    expect(parseScopeFrame(frame(1, -41))).toMatchObject({ row: { level: -41, tx: true } });
    expect(parseScopeFrame(history([{ flags: 0, level: -30, age: 7, bin: 0 }]))).toMatchObject({
      history: { clock: CLOCK, rows: [{ age: 7, row: { level: -30 } }] },
    });
    const other = new Uint8Array(frame(0, 0));
    other[0] = 9;
    expect(parseScopeFrame(other.buffer)).toBeNull();
    expect(parseScopeFrame(Uint8Array.of(9).buffer)).toBeNull();
    expect(parseScopeRow(history([{ flags: 0, level: -30, age: 7, bin: 0 }]))).toBeNull(); // (the parser of a row alone, which is all a page of the version before has: it takes the rows kept for no row)
  });
});
