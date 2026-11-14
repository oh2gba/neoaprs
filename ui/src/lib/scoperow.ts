// A row of the HF radio's waterfall as the daemon sends it: a binary frame of the page's socket (PROTOCOL.md, Binary frames; neoaprs/mercuryscope.py makes it), and the frame of the rows the daemon kept, which a page is sent when it
// begins to look, with the daemon's clock and each row with its age. The bins are bytes on the modem's own scale, which is the scale lib/waterfallfloor.ts reads: this turns them into the modem's dB.
import { LIMITS } from "@/protocol/lists";

const { rowBins, rowOffsetDb, rowStepDb } = LIMITS.scope;

/** The kind of frame a row is: the first byte. A frame of another kind is not a row. */
export const ROW_KIND = 1;
/** The kind of frame the rows kept are. */
export const HISTORY_KIND = 2;
const HEADER_BYTES = 3;
const HISTORY_HEADER_BYTES = 9; // the kind and the daemon's clock (milliseconds since 1970, a little-endian float64) of the rows kept
const KEPT_HEADER_BYTES = 6; // the flags, the level and the age (four bytes, little-endian) of a row kept
const TX_FLAG = 1;

/** One row: the passband's bins in the modem's dB (the first is the modem's bin `rowFirstBin`), the level of the passband in dBFS, and whether the radio transmitted (the row is then of our own signal). */
export interface ScopeRow {
  db: Float32Array;
  level: number;
  tx: boolean;
}

/** A row kept by the daemon, and how many milliseconds before the frame was made it was made. */
export interface AgedRow {
  row: ScopeRow;
  age: number;
}

/** The rows kept, oldest first (none: forget what is held), and the daemon's clock when it sent them, milliseconds since 1970. */
export interface ScopeHistory {
  rows: AgedRow[];
  clock: number;
}

/** What a binary frame holds: a row, or the rows kept. */
export type ScopeFrame = { row: ScopeRow } | { history: ScopeHistory };

/** The modem's dB a byte of a row stands for. */
export const dbOfRowByte = (byte: number): number => rowOffsetDb + byte * rowStepDb;

/** The row whose flags and level stand at `at` and whose bins begin at `bins`. */
function rowAt(view: DataView, at: number, bins: number): ScopeRow {
  const bytes = new Uint8Array(view.buffer, view.byteOffset + bins, rowBins);
  return { db: Float32Array.from(bytes, dbOfRowByte), level: view.getInt8(at + 1), tx: (view.getUint8(at) & TX_FLAG) !== 0 };
}

/** The row in a frame, or null for a frame that is no row: of another kind or of another size. */
export function parseScopeRow(data: ArrayBuffer): ScopeRow | null {
  if (data.byteLength !== HEADER_BYTES + rowBins) return null;
  const view = new DataView(data);
  if (view.getUint8(0) !== ROW_KIND) return null;
  return rowAt(view, 1, HEADER_BYTES);
}

/** The rows kept in a frame and the daemon's clock, or null for a frame that is not of them: of another kind, or not a whole number of rows. */
export function parseScopeHistory(data: ArrayBuffer): ScopeHistory | null {
  const size = KEPT_HEADER_BYTES + rowBins;
  if (data.byteLength < HISTORY_HEADER_BYTES || (data.byteLength - HISTORY_HEADER_BYTES) % size !== 0) return null;
  const view = new DataView(data);
  if (view.getUint8(0) !== HISTORY_KIND) return null;
  const rows: AgedRow[] = [];
  for (let at = HISTORY_HEADER_BYTES; at < data.byteLength; at += size)
    rows.push({ row: rowAt(view, at, at + KEPT_HEADER_BYTES), age: view.getUint32(at + 2, true) });
  return { rows, clock: view.getFloat64(1, true) };
}

/** What a binary frame holds, or null for a frame of a kind this page does not know: more may come, and it is let go. */
export function parseScopeFrame(data: ArrayBuffer): ScopeFrame | null {
  const row = parseScopeRow(data);
  if (row !== null) return { row };
  const history = parseScopeHistory(data);
  return history === null ? null : { history };
}
