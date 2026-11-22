// What the page keeps of the HF radio's waterfall outside any picture, so a picture opened again
// is drawn whole at once: the rows of the last two minutes (as sent by the daemon and as the
// floor draws them, lib/waterfallfloor.ts), each stamped with this page's clock, and the stations
// heard in that time, with the modem's SNR where the page saw it.
// The rows the daemon kept (lib/scoperow.ts `ScopeHistory`) fill the time no picture looked: if
// they continue from the newest row held, only the newer ones are taken; else they replace all.
// They carry the daemon's clock, which places a heard station at the time the daemon wrote.
// The page clock never goes back (`performance.now`), however the computer's clock is set.
// Pictures subscribe with `listen`.
import type { AgedRow, ScopeHistory, ScopeRow } from "@/lib/scoperow";
import { RowFeed } from "@/lib/waterfallfloor";
import { LIMITS } from "@/protocol/lists";

/** Rows are kept as long as the daemon keeps them. */
const KEEP_MS = LIMITS.scope.historySec * 1000;
/**
 * The rows the daemon kept continue from the newest row held if that row is among them within
 * this much of its arrival (their age is counted on the daemon's clock plus the transit time).
 */
const MATCH_MS = 5000;
/**
 * A station whose daemon time is within this much of now was heard just now: it is placed at now
 * with the modem's SNR (the time is in whole seconds and the packet takes a tick to arrive).
 */
const FRESH_MS = 3000;
/** Times are in whole seconds, so a station told later is placed in the middle of its second. */
const HALF_SECOND_MS = 500;

/** A kept row: as it came, its time on this page's clock, and as the floor draws it. */
export interface KeptRow {
  row: ScopeRow;
  at: number;
  bytes: Uint8Array;
  tx: boolean;
}

/**
 * A station heard on the HF radio: when (page clock), its call and the modem's SNR (null if
 * unseen).
 */
export interface Heard {
  at: number;
  call: string;
  snr: number | null;
}

/**
 * A heard station as kept; `wall` is the daemon's time, null if placed at the moment it was told.
 */
type Written = Heard & { wall: number | null };

/** What a picture is told; each is optional. */
export interface ScopeListener {
  row?: (kept: KeptRow) => void;
  heard?: (heard: Heard) => void;
  /** everything is to be read again (the daemon's rows arrived) */
  whole?: () => void;
}

const same = (a: ScopeRow, b: ScopeRow): boolean => a.level === b.level && a.tx === b.tx && a.db.every((db, i) => db === b.db[i]);

export class ScopeMemory {
  // oldest first
  private kept: KeptRow[] = [];
  private told: Written[] = [];
  private feed = new RowFeed();
  private readonly listeners = new Set<ScopeListener>();
  // this page's clock less the daemon's; 0 until the daemon's rows say otherwise
  private offset = 0;
  // the latest moment told, and the steady clock then
  private mark = { at: -Infinity, steady: 0 };

  /** `steady` is a clock that only goes forward. */
  constructor(
    private readonly clock: () => number = Date.now,
    private readonly steady: () => number = clock === Date.now ? () => performance.now() : clock,
  ) {}

  /**
   * The current time on the clock rows are placed by: the computer's, never before the last moment
   * told plus elapsed time.
   */
  now(): number {
    const steady = this.steady();
    const at = Math.max(this.clock(), this.mark.at + steady - this.mark.steady);
    this.mark = { at, steady };
    return at;
  }

  get rows(): readonly KeptRow[] {
    return this.kept;
  }

  get heard(): readonly Heard[] {
    return this.told;
  }

  /** Subscribe; the returned function unsubscribes. */
  listen(listener: ScopeListener): () => void {
    this.listeners.add(listener);
    return () => void this.listeners.delete(listener);
  }

  /** A row arrived and was made now. */
  live(row: ScopeRow): void {
    const kept = this.take(row, Math.max(this.now(), this.kept.at(-1)?.at ?? -Infinity));
    this.kept.push(kept);
    this.forget();
    this.listeners.forEach((listener) => listener.row?.(kept));
  }

  /**
   * The daemon's kept rows arrived (oldest first, with ages) along with its clock; stations told
   * later are placed again by that clock. No rows means the daemon kept none.
   */
  history({ rows, clock }: ScopeHistory): void {
    const now = this.now();
    this.offset = now - clock;
    for (const heard of this.told) if (heard.wall !== null) heard.at = heard.wall + this.offset + HALF_SECOND_MS;
    this.told.sort((a, b) => a.at - b.at);
    const from = this.goesOn(rows, now);
    if (from === null) {
      this.feed = new RowFeed();
      this.kept = rows.map(({ row, age }) => this.take(row, now - age));
    } else {
      let last = this.kept.at(-1)!.at;
      for (const { row, age } of rows.slice(from + 1)) {
        last = Math.max(last, now - age);
        this.kept.push(this.take(row, last));
      }
    }
    this.forget();
    this.listeners.forEach((listener) => listener.whole?.());
  }

  /**
   * A station was heard at `wall` (the daemon's clock, a packet's `heard_at`); `snr` is the modem's
   * latest SNR. One heard just now is placed at now with that SNR; one told later is placed at its
   * time on this page's clock with the call alone.
   */
  hear(call: string, snr: number | null, wall: number): void {
    const now = this.now();
    const fresh = Math.abs(wall + this.offset - now) <= FRESH_MS;
    const heard: Written = fresh ? { at: now, call, snr, wall: null } : { at: wall + this.offset + HALF_SECOND_MS, call, snr: null, wall };
    if (heard.at < now - KEEP_MS) return;
    // Keep `told` ordered; a station heard just now goes at the end.
    let at = this.told.length;
    while (at > 0 && this.told[at - 1].at > heard.at) at--;
    this.told.splice(at, 0, heard);
    // Also needed for a radio whose rows never come: its heard stations expire like rows.
    this.forget();
    this.listeners.forEach((listener) => listener.heard?.(heard));
  }

  private take(row: ScopeRow, at: number): KeptRow {
    return { row, at, ...this.feed.take(row, at) };
  }

  /**
   * The index in `rows` of the newest row held, so only later ones are new; null if it is not there
   * (nothing held, the daemon forgot, or what is held does not reach back as far).
   */
  private goesOn(rows: readonly AgedRow[], now: number): number | null {
    const newest = this.kept.at(-1);
    const oldest = this.kept[0];
    if (!newest || !oldest || rows.length === 0 || oldest.at > now - rows[0].age + MATCH_MS) return null;
    const before = this.kept.at(-2);
    // Of equal rows, the one nearest the moment the held row arrived.
    let found: number | null = null;
    for (let i = rows.length - 1; i >= 0; i--) {
      const off = Math.abs(now - rows[i].age - newest.at);
      if (now - rows[i].age < newest.at - MATCH_MS) break;
      if (off > MATCH_MS || !same(rows[i].row, newest.row) || (before && !(i > 0 && same(rows[i - 1].row, before.row)))) continue;
      if (found === null || off < Math.abs(now - rows[found].age - newest.at)) found = i;
    }
    return found;
  }

  /** Drop what is older than the time kept. */
  private forget(): void {
    const oldest = this.now() - KEEP_MS;
    const first = this.kept.findIndex((kept) => kept.at >= oldest);
    if (first !== 0) this.kept = first < 0 ? [] : this.kept.slice(first);
    if (this.told.length > 0 && this.told[0].at < oldest) this.told = this.told.filter((heard) => heard.at >= oldest);
  }
}
