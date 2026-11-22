// The lines of the HF radio's waterfall on the time axis: a line is a fifth of a second of the
// page's clock (LINE_MS; two fifths at the Slow speed, PACE in waterfall.ts). A row goes in the
// line of the moment it was made, so a row from forty seconds ago stands forty seconds down
// whether live or kept by the daemon, and time without rows is a gap of as many lines. The
// painter (waterfallpainter.ts) draws them; waterfall.ts has what a line is made of.
import { LINES_PER_SECOND, keptLines, lineOf, quarterIn, silentOwn } from "@/lib/waterfall";

/** A line is this many milliseconds of the page's clock: five lines a second. */
const LINE_MS = 1000 / LINES_PER_SECOND;
/**
 * The number of the line a moment (ms of the page's clock) falls in, for the given line length.
 */
const slotOf = (at: number, lineMs = LINE_MS): number => Math.floor(at / lineMs);
/**
 * A line with no row (rows come about every 120 ms, a line is 200) repeats the line before it
 * while the newest row is less than this older than the line; after that it is the ground: the
 * modem has been away.
 */
const HOLD_MS = 500;

/**
 * A row as the painter is given it: its bytes over the floor, when it was made (page clock),
 * and whether it is our own.
 */
export interface DrawnRow {
  bytes: Uint8Array;
  at: number;
  tx: boolean;
}

/**
 * A line of the picture: its number, its start time, its bytes (null: the ground), whether it
 * is our own transmission, whether it repeats the line before (no row came in it), and the
 * quarter-minute whose time is written on it (`quarter`, with `time` saying there is one).
 */
export interface Line {
  slot: number;
  at: number;
  bytes: Uint8Array | null;
  tx: boolean;
  held: boolean;
  time: boolean;
  quarter: number | null;
}

/**
 * The lines, one per slot from the oldest kept to the newest whole one, newest first, and the
 * rows of the slot not yet whole. A line is either our own transmission or what was heard,
 * never both: when we begin or stop sending within a slot, the rows gathered before are
 * dropped. A row of ours with nothing in it gathers nothing, so a transmission starts with
 * clean edges.
 */
export class Lines {
  lines: Line[] = [];
  /** How many lines are kept: two minutes of them. */
  readonly kept: number;
  private open: { slot: number; rows: Uint8Array[]; tx: boolean } | null = null;
  private last = -Infinity; // the time of the newest row
  /** Whether the newest row is our own transmission. */
  sending = false;

  constructor(readonly lineMs = LINE_MS) {
    this.kept = keptLines(lineMs);
  }

  /** The number of the line the moment `at` falls in. */
  slot(at: number): number {
    return slotOf(at, this.lineMs);
  }

  /** The number of the newest whole line; -Infinity before the first. */
  get top(): number {
    return this.lines[0]?.slot ?? -Infinity;
  }

  /**
   * Add a row; returns how many lines it made whole (the picture moves down by as many). A
   * row older than the newest whole line goes in the slot after it: the page's clock went
   * back.
   */
  add(row: DrawnRow): number {
    const slot = Math.max(this.slot(row.at), this.top + 1, this.open?.slot ?? -Infinity);
    const added = this.until(slot);
    if (!this.open) this.open = { slot, rows: [], tx: row.tx };
    if (row.tx !== this.open.tx) this.open = { slot, rows: [], tx: row.tx };
    if (!row.tx || !silentOwn(row.bytes)) this.open.rows.push(row.bytes);
    [this.last, this.sending] = [Math.max(this.last, row.at), row.tx];
    return added;
  }

  /**
   * Make every line before `slot` whole: the slot being gathered and slots no row came in.
   * Returns how many.
   */
  until(slot: number): number {
    const first = this.lines.length > 0 ? this.top + 1 : Math.min(this.open?.slot ?? slot, slot);
    let added = 0;
    for (let at = Math.max(first, slot - this.kept); at < slot; at++, added++) this.put(this.open?.slot === at ? this.gathered() : this.empty(at));
    if (this.open && this.open.slot < slot) this.open = null;
    return added;
  }

  /**
   * Rebuild from the rows (oldest first), making every line before the one `now` is in whole.
   */
  build(rows: readonly DrawnRow[], now: number): void {
    [this.lines, this.open, this.last, this.sending] = [[], null, -Infinity, false];
    for (const row of rows) this.add(row);
    if (rows.length > 0) this.until(Math.max(this.slot(now), this.top + 1));
  }

  /**
   * The newest `count` lines with something heard or sent in them, newest first (a repeated
   * line is not counted twice).
   */
  newest(count: number): Line[] {
    const out: Line[] = [];
    for (const line of this.lines) {
      if (out.length >= count) break;
      if (line.bytes !== null && !line.held) out.push(line);
    }
    return out;
  }

  private gathered(): Line {
    const open = this.open!;
    return this.line(open.slot, open.rows.length > 0 ? lineOf(open.rows, open.tx) : null, open.tx, false);
  }

  private empty(slot: number): Line {
    const before = this.lines[0];
    if (before && slot * this.lineMs - this.last < HOLD_MS) return this.line(slot, before.bytes, before.tx, true);
    return this.line(slot, null, false, false);
  }

  private line(slot: number, bytes: Uint8Array | null, tx: boolean, held: boolean): Line {
    const at = slot * this.lineMs;
    const quarter = quarterIn(at, this.lineMs);
    return { slot, at, bytes, tx, held, time: quarter !== null, quarter };
  }

  private put(line: Line): void {
    this.lines.unshift(line);
    if (this.lines.length > this.kept) this.lines.length = this.kept;
  }
}
