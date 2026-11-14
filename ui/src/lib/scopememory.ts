// What the page keeps of the HF radio's waterfall, outside every picture, so that a picture opened again (another tab and back, the monitor card closed and opened) is drawn whole at once: the rows of the last two minutes, as
// the daemon sent them and as the floor tells them (lib/waterfallfloor.ts, one floor for the page), each at the moment it was made by this page's clock; and what was heard on the HF radio in that time, with the modem's SNR where
// the page was there to read it. The rows the daemon kept (lib/scoperow.ts, `ScopeHistory`) fill the time no picture looked: where they go on from the newest row held, only the newer ones are taken (the rows held, their times and
// the floor stay as they are); else they are all of it. They say the daemon's clock too, by which a station heard is placed at the time the daemon wrote, on this page's clock. The page's clock here never goes back: a row
// comes after the one before it by as much as passed (`performance.now`), however the computer's clock is set meanwhile. The pictures listen (`listen`): a row, a heard station, or all of it again.
import type { AgedRow, ScopeHistory, ScopeRow } from "@/lib/scoperow";
import { RowFeed } from "@/lib/waterfallfloor";
import { LIMITS } from "@/protocol/lists";

/** The rows are kept as long as the daemon keeps them. */
const KEEP_MS = LIMITS.scope.historySec * 1000;
/** The rows the daemon kept are found to go on from the newest row held when that row is among them within this much of the moment it came: their age is counted on the daemon's clock and the time it took to come. */
const MATCH_MS = 5000;
/** A station whose time, as the daemon wrote it, is within this much of the moment it is told was heard just now: it is placed at that moment, with the modem's SNR of it (the time is in whole seconds, and the packet takes a tick to come). */
const FRESH_MS = 3000;
/** The daemon writes a time in whole seconds: a station told later is placed in the middle of its second. */
const HALF_SECOND_MS = 500;

/** A row kept: as it came, the moment it was made by this page's clock, and as the floor tells it (its bytes, and whether it is drawn as our own). */
export interface KeptRow {
  row: ScopeRow;
  at: number;
  bytes: Uint8Array;
  tx: boolean;
}

/** A station heard on the HF radio: when (this page's clock), its call, and the modem's SNR of it (null where the page did not see it come). */
export interface Heard {
  at: number;
  call: string;
  snr: number | null;
}

/** A station heard as it is kept: also the time the daemon wrote, by which it is placed again when the daemon's clock is known better; null where it was placed at the moment it was told. */
type Written = Heard & { wall: number | null };

/** What a picture is told; each is optional. */
export interface ScopeListener {
  row?: (kept: KeptRow) => void;
  heard?: (heard: Heard) => void;
  /** everything is to be read again: the rows the daemon kept came */
  whole?: () => void;
}

const same = (a: ScopeRow, b: ScopeRow): boolean => a.level === b.level && a.tx === b.tx && a.db.every((db, i) => db === b.db[i]);

export class ScopeMemory {
  private kept: KeptRow[] = []; // oldest first
  private told: Written[] = [];
  private feed = new RowFeed();
  private readonly listeners = new Set<ScopeListener>();
  private offset = 0; // this page's clock less the daemon's, as the latest rows kept said (none yet: the two are taken to agree)
  private mark = { at: -Infinity, steady: 0 }; // the latest moment told, and the steady clock then

  /** `steady` is a clock that only goes forward (a clock a test holds is its own). */
  constructor(
    private readonly clock: () => number = Date.now,
    private readonly steady: () => number = clock === Date.now ? () => performance.now() : clock,
  ) {}

  /** The moment it is, by the clock the rows are placed by: the computer's, but never before the moment told last and the time that passed since. */
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

  /** Listens; the function it returns stops it. */
  listen(listener: ScopeListener): () => void {
    this.listeners.add(listener);
    return () => void this.listeners.delete(listener);
  }

  /** A row came: it was made now. */
  live(row: ScopeRow): void {
    const kept = this.take(row, Math.max(this.now(), this.kept.at(-1)?.at ?? -Infinity));
    this.kept.push(kept);
    this.forget();
    this.listeners.forEach((listener) => listener.row?.(kept));
  }

  /** The rows the daemon kept came, oldest first with their ages (none: it kept none, and nothing held is true any more), and its clock: the stations told later are placed again by it. */
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

  /** A station was heard at `wall`, the daemon's clock (a packet's `heard_at`), and `snr` is the modem's SNR of the latest frame now. One heard just now is placed at this moment with that SNR; one told later (the socket
   * was away, the browser held the page) at its time on this page's clock, with the call alone. */
  hear(call: string, snr: number | null, wall: number): void {
    const now = this.now();
    const fresh = Math.abs(wall + this.offset - now) <= FRESH_MS;
    const heard: Written = fresh ? { at: now, call, snr, wall: null } : { at: wall + this.offset + HALF_SECOND_MS, call, snr: null, wall };
    if (heard.at < now - KEEP_MS) return;
    this.told.push(heard);
    this.told.sort((a, b) => a.at - b.at);
    this.listeners.forEach((listener) => listener.heard?.(heard));
  }

  private take(row: ScopeRow, at: number): KeptRow {
    return { row, at, ...this.feed.take(row, at) };
  }

  /** Where in the rows the daemon kept the newest row held is, so that only those after it are new; null where it is not (nothing held, the daemon forgot, or what is held does not reach as far back as they do). */
  private goesOn(rows: readonly AgedRow[], now: number): number | null {
    const newest = this.kept.at(-1);
    const oldest = this.kept[0];
    if (!newest || !oldest || rows.length === 0 || oldest.at > now - rows[0].age + MATCH_MS) return null;
    const before = this.kept.at(-2);
    let found: number | null = null; // (of rows that are the same, the one nearest the moment the row held came)
    for (let i = rows.length - 1; i >= 0; i--) {
      const off = Math.abs(now - rows[i].age - newest.at);
      if (now - rows[i].age < newest.at - MATCH_MS) break;
      if (off > MATCH_MS || !same(rows[i].row, newest.row) || (before && !(i > 0 && same(rows[i - 1].row, before.row)))) continue;
      if (found === null || off < Math.abs(now - rows[found].age - newest.at)) found = i;
    }
    return found;
  }

  /** What is older than the time kept is let go. */
  private forget(): void {
    const oldest = this.now() - KEEP_MS;
    const first = this.kept.findIndex((kept) => kept.at >= oldest);
    if (first !== 0) this.kept = first < 0 ? [] : this.kept.slice(first);
    if (this.told.length > 0 && this.told[0].at < oldest) this.told = this.told.filter((heard) => heard.at >= oldest);
  }
}
