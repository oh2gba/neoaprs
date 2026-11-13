import { describe, expect, it } from "vitest";
import { LIMITS } from "@/protocol/lists";
import { ROW_KIND, dbOfRowByte, parseScopeRow } from "@/lib/scoperow";

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
