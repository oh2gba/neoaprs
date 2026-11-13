// A row of the HF radio's waterfall as the daemon sends it: a binary frame of the page's socket (PROTOCOL.md, Binary frames; neoaprs/mercuryscope.py makes it). The bins are bytes on the modem's own scale, which is the
// scale lib/waterfallfloor.ts reads: this turns them into the modem's dB.
import { LIMITS } from "@/protocol/lists";

const { rowBins, rowOffsetDb, rowStepDb } = LIMITS.scope;

/** The kind of frame a row is: the first byte. A frame of another kind is not a row. */
export const ROW_KIND = 1;
const HEADER_BYTES = 3;
const TX_FLAG = 1;

/** One row: the passband's bins in the modem's dB (the first is the modem's bin `rowFirstBin`), the level of the passband in dBFS, and whether the radio transmitted (the row is then of our own signal). */
export interface ScopeRow {
  db: Float32Array;
  level: number;
  tx: boolean;
}

/** The modem's dB a byte of a row stands for. */
export const dbOfRowByte = (byte: number): number => rowOffsetDb + byte * rowStepDb;

/** The row in a frame, or null for a frame that is no row: of another kind or of another size. */
export function parseScopeRow(data: ArrayBuffer): ScopeRow | null {
  if (data.byteLength !== HEADER_BYTES + rowBins) return null;
  const view = new DataView(data);
  if (view.getUint8(0) !== ROW_KIND) return null;
  const bytes = new Uint8Array(data, HEADER_BYTES);
  return { db: Float32Array.from(bytes, dbOfRowByte), level: view.getInt8(2), tx: (view.getUint8(1) & TX_FLAG) !== 0 };
}
