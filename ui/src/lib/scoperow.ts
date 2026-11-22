// A waterfall row as the daemon sends it: a binary frame of the page's socket (PROTOCOL.md, Binary
// frames; neoaprs/mercuryscope.py), and the frame of rows the daemon kept, each with its age and
// the
// daemon's clock. Bins are bytes on the modem's scale (read by lib/waterfallfloor.ts); this turns
// them into dB. Each frame comes wrapped in a frame naming its radio (`RADIO_KIND`).
import type { RadioId } from "@/lib/radios";
import { LIMITS } from "@/protocol/lists";

const { rowBins, rowOffsetDb, rowStepDb } = LIMITS.scope;

/** The kind of frame a row is: the first byte. Another kind is not a row. */
export const ROW_KIND = 1;
/** The kind of frame the kept rows are. */
export const HISTORY_KIND = 2;
/**
 * A frame of one radio's scope: the kind, the radio id (little-endian uint32), then a whole frame
 * of the kinds above.
 */
export const RADIO_KIND = 3;
const RADIO_HEADER_BYTES = 5;
const HEADER_BYTES = 3;
// kind, then the daemon's clock (ms since 1970, little-endian float64)
const HISTORY_HEADER_BYTES = 9;
// flags, level, then the age (little-endian uint32)
const KEPT_HEADER_BYTES = 6;
const TX_FLAG = 1;

/**
 * One row: the passband's bins in modem dB (the first is `rowFirstBin`), its level in dBFS, and
 * `tx` (our own signal).
 */
export interface ScopeRow {
  db: Float32Array;
  level: number;
  tx: boolean;
}

/** A row kept by the daemon and its age in ms when the frame was made. */
export interface AgedRow {
  row: ScopeRow;
  age: number;
}

/**
 * The kept rows, oldest first (none: forget what is held), and the daemon's clock in ms since 1970.
 */
export interface ScopeHistory {
  rows: AgedRow[];
  clock: number;
}

/** What a binary frame holds: a row or the kept rows, and the radio they belong to. */
export type ScopeFrame = ({ row: ScopeRow } | { history: ScopeHistory }) & { radio: RadioId };

/** The modem dB a row byte stands for. */
export const dbOfRowByte = (byte: number): number => rowOffsetDb + byte * rowStepDb;

/** The row whose flags and level are at `at` and whose bins start at `bins`. */
function rowAt(view: DataView, at: number, bins: number): ScopeRow {
  const bytes = new Uint8Array(view.buffer, view.byteOffset + bins, rowBins);
  return {
    db: Float32Array.from(bytes, dbOfRowByte),
    level: view.getInt8(at + 1),
    tx: (view.getUint8(at) & TX_FLAG) !== 0,
  };
}

/** The row in a frame; null if the frame is of another kind or size. */
export function parseScopeRow(data: ArrayBuffer): ScopeRow | null {
  if (data.byteLength !== HEADER_BYTES + rowBins) return null;
  const view = new DataView(data);
  if (view.getUint8(0) !== ROW_KIND) return null;
  return rowAt(view, 1, HEADER_BYTES);
}

/** The kept rows and the daemon's clock; null if of another kind or not a whole number of rows. */
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

/** The radio and the inner frame of a radio scope frame; null for another kind. */
export function radioFrame(data: ArrayBuffer): { radio: RadioId; frame: ArrayBuffer } | null {
  if (data.byteLength <= RADIO_HEADER_BYTES) return null;
  const view = new DataView(data);
  if (view.getUint8(0) !== RADIO_KIND) return null;
  return { radio: view.getUint32(1, true), frame: data.slice(RADIO_HEADER_BYTES) };
}

/**
 * What a binary frame holds and whose scope it is; null for an unknown kind or no radio (ignored).
 */
export function parseScopeFrame(data: ArrayBuffer): ScopeFrame | null {
  const named = radioFrame(data);
  if (named === null) return null;
  const row = parseScopeRow(named.frame);
  if (row !== null) return { row, radio: named.radio };
  const history = parseScopeHistory(named.frame);
  return history === null ? null : { history, radio: named.radio };
}
