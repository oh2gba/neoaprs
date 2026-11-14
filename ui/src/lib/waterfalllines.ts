// The lines of the HF radio's waterfall on the time axis: a line is a fifth of a second of the page's clock (LINE_MS), and a row is in the line of the moment it was made, so that a row made forty seconds ago stands forty
// seconds down whether it came live or among the rows the daemon kept, and time without rows is a gap of as many lines. The painter (lib/waterfallpainter.ts) draws them; lib/waterfall.ts has what a line is made of.
import { KEPT_LINES, LINES_PER_SECOND, lineOf, silentOwn, startsQuarter } from "@/lib/waterfall";

/** A line is this many milliseconds of the page's clock: five lines a second. */
const LINE_MS = 1000 / LINES_PER_SECOND;
/** The number of the line a moment (milliseconds of the page's clock) falls in: they count up with the time. */
export const slotOf = (at: number): number => Math.floor(at / LINE_MS);
/** A line no row came in (the rows come about every 120 ms, a line is 200) is the line before it again while the newest row is less than this older than the line; after that it is the ground: the modem has been away. */
const HOLD_MS = 500;

/** A row as the painter is given it: its bytes over the floor (lib/waterfallfloor.ts), when it was made by the page's clock, and whether it is drawn as our own. */
export interface DrawnRow {
  bytes: Uint8Array;
  at: number;
  tx: boolean;
}

/** A line of the picture: its number, the time it begins, its bytes (null: nothing in it, the ground), whether it is of our own transmission, whether it is the line before it again (no row came in it), and whether the time is
 * written on it (the first of a quarter of a minute). */
export interface Line {
  slot: number;
  at: number;
  bytes: Uint8Array | null;
  tx: boolean;
  held: boolean;
  time: boolean;
}

/** The lines, one for every slot from the oldest kept to the newest that is whole, the newest first, and the rows of the slot that is not yet whole. A line is either of our own transmission or of what is heard, never of both:
 * when we begin or stop sending within a slot, the rows of it gathered before are let go and the slot is of the new state; a row of ours with nothing in it gathers nothing, so a transmission's first lines are the ground
 * with the mark of a transmission and its edges are clean. */
export class Lines {
  lines: Line[] = [];
  private open: { slot: number; rows: Uint8Array[]; tx: boolean } | null = null;
  private last = -Infinity; // the time of the newest row
  /** whether the newest row is of our own transmission */
  sending = false;

  /** The number of the newest whole line; -Infinity before the first. */
  get top(): number {
    return this.lines[0]?.slot ?? -Infinity;
  }

  /** A row; how many lines it made whole (the picture moves down by as many). A row older than the newest line whole is taken as of the slot after it: the page's clock went back. */
  add(row: DrawnRow): number {
    const slot = Math.max(slotOf(row.at), this.top + 1, this.open?.slot ?? -Infinity);
    const added = this.until(slot);
    if (!this.open) this.open = { slot, rows: [], tx: row.tx };
    if (row.tx !== this.open.tx) this.open = { slot, rows: [], tx: row.tx };
    if (!row.tx || !silentOwn(row.bytes)) this.open.rows.push(row.bytes);
    [this.last, this.sending] = [Math.max(this.last, row.at), row.tx];
    return added;
  }

  /** Makes every line before `slot` whole: the slot being gathered, and the slots no row came in. Says how many there are. */
  until(slot: number): number {
    const first = this.lines.length > 0 ? this.top + 1 : Math.min(this.open?.slot ?? slot, slot);
    let added = 0;
    for (let at = Math.max(first, slot - KEPT_LINES); at < slot; at++, added++) this.put(this.open?.slot === at ? this.gathered() : this.empty(at));
    if (this.open && this.open.slot < slot) this.open = null;
    return added;
  }

  /** All again from the rows (oldest first), and every line before the one `now` is in made whole: the picture as it stands at that moment. */
  build(rows: readonly DrawnRow[], now: number): void {
    [this.lines, this.open, this.last, this.sending] = [[], null, -Infinity, false];
    for (const row of rows) this.add(row);
    if (rows.length > 0) this.until(Math.max(slotOf(now), this.top + 1));
  }

  /** The newest lines that have something heard or sent in them, up to `count`, the newest first (a line that is the one before it again is not counted twice). */
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
    if (before && slot * LINE_MS - this.last < HOLD_MS) return this.line(slot, before.bytes, before.tx, true);
    return this.line(slot, null, false, false);
  }

  private line(slot: number, bytes: Uint8Array | null, tx: boolean, held: boolean): Line {
    const at = slot * LINE_MS;
    return { slot, at, bytes, tx, held, time: startsQuarter(at - LINE_MS, at) };
  }

  private put(line: Line): void {
    this.lines.unshift(line);
    if (this.lines.length > KEPT_LINES) this.lines.length = KEPT_LINES;
  }
}
