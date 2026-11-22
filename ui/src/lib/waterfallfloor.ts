// The floor under the HF radio's waterfall: the noise each bin has when nothing is on it, found
// from the rows themselves, so the picture shows each bin's dB over its own floor and no gain needs
// setting. Also the feed that turns the daemon's rows (lib/scoperow.ts, modem dB) into the bytes
// the painter takes.
import type { ScopeRow } from "@/lib/scoperow";
import { BINS, ROWS_PER_SECOND, byteOfDb, hzOfBin } from "@/lib/waterfall";
import { LIMITS } from "@/protocol/lists";

const { signalLoHz, signalHiHz } = LIMITS.scope;

function quantile(values: ArrayLike<number>, q: number): number {
  const sorted = Float32Array.from(values).sort();
  return sorted[Math.floor(q * (sorted.length - 1))];
}

/**
 * Each value as `pick` of the values within `half` bins each side, fewer at the ends so the window
 * stays even.
 */
function windowed(values: Float32Array, half: number, pick: (window: Float32Array) => number): Float32Array {
  return values.map((_, i) => {
    const reach = Math.min(half, i, values.length - 1 - i);
    return pick(values.subarray(i - reach, i + reach + 1));
  });
}

const LEVEL_QUANTILE = 0.25; // a row's level is read a quarter up from its quietest bin, as the daemon's meter does
// among bins this far or more from a frame's band, so a frame does not darken the noise beside it
const LEVEL_CLEAR_HZ = 100;
const LEVEL_GAIN = 0.1; // the level moves this part of the way to a row's reading (about a second)
// at most this much per row: static moves it under 1 dB, a 10 dB step is followed in four seconds
const LEVEL_SLEW_DB = 0.3;
const BLOCK_ROWS = ROWS_PER_SECOND; // the shape is learnt from per-second bin means
const SHAPE_BLOCKS = 30; // over the last half minute
// as the third lowest: a bin's reading with nothing on it, despite frames and audio dropouts
const SHAPE_QUANTILE = 0.1;
// smooth over 300 Hz: the median over that width does not see a carrier, however long it stays
const SHAPE_MEDIAN_HALF = 20;
const SHAPE_SMOOTH_HALF = 4;
const median = (window: ArrayLike<number>): number => quantile(window, 0.5);
const CLEAR_BINS = Array.from({ length: BINS }, (_, i) => i).filter(
  (i) => hzOfBin(i) < signalLoHz - LEVEL_CLEAR_HZ || hzOfBin(i) > signalHiHz + LEVEL_CLEAR_HZ,
);

/**
 * The floor under the waterfall: each bin's noise with nothing on it, in the modem's dB, found from
 * the rows. It is the level of the passband now (it follows noise changes within seconds) plus the
 * passband's shape bin by bin, learnt slowly because a receiver's filter is not flat. A carrier is
 * narrower than the shape is smooth, and a frame is excluded (level read beside its band, shape
 * from quiet seconds), so neither moves it; a lasting change is taken in within half a minute. Rows
 * of our own transmission are not fed.
 */
export class Floor {
  private level: number | null = null;
  private readonly offset = new Float32Array(BINS); // how far each bin's floor is over the level
  private middle = 0; // median of them
  // each bin's offset about that middle, taken off a row before its level is read
  private tilt = new Float32Array(BINS);
  private blocks: Float32Array[] = [];
  private readonly sum = new Float64Array(BINS);
  private count = 0;

  /**
   * The level a row reads: its quiet quarter beside the band of a frame, the shape taken off first.
   */
  private read(row: Float32Array, tilt: Float32Array): number {
    return quantile(
      CLEAR_BINS.map((i) => row[i] - tilt[i]),
      LEVEL_QUANTILE,
    );
  }

  feed(row: Float32Array): void {
    const reading = this.read(row, this.tilt);
    this.level = this.level === null ? reading : this.level + Math.max(-LEVEL_SLEW_DB, Math.min(LEVEL_SLEW_DB, LEVEL_GAIN * (reading - this.level)));
    // relative to the row's own reading, not the level still on its way: a noise step is no dip in
    // a bin
    for (let i = 0; i < BINS; i++) this.sum[i] += 10 ** ((row[i] - reading) / 10);
    this.count++;
    const full = this.count === BLOCK_ROWS;
    if (!full && this.blocks.length > 0) return;
    // Each bin's one-second mean over the readings, median-smoothed across bins: a carrier is gone
    // from it, and it is steady enough that the lowest of thirty is hardly lower than the rest.
    const block = windowed(
      Float32Array.from(this.sum, (power) => 10 * Math.log10(power / this.count + 1e-30)),
      SHAPE_MEDIAN_HALF,
      median,
    );
    if (full) {
      this.blocks = [block, ...this.blocks.slice(0, SHAPE_BLOCKS - 1)];
      this.sum.fill(0);
      this.count = 0;
    }
    // in the first second, from the rows there are, so the first row is drawn over a floor
    this.learn(full ? this.blocks : [block], row);
  }

  /**
   * The shape from the seconds kept. A new shape changes what a row reads as its level (`row` is
   * the newest), so the level and what was learnt over the readings move by as much and the floor
   * does not jump.
   */
  private learn(blocks: readonly Float32Array[], row: Float32Array): void {
    const low = Math.floor(SHAPE_QUANTILE * (blocks.length - 1));
    const column = new Float32Array(blocks.length);
    const quiet = Float32Array.from({ length: BINS }, (_, i) => {
      blocks.forEach((block, n) => (column[n] = block[i]));
      return column.sort()[low];
    });
    const offset = windowed(quiet, SHAPE_SMOOTH_HALF, (w) => w.reduce((a, b) => a + b, 0) / w.length);
    const middle = median(offset);
    const tilt = offset.map((v) => v - middle);
    const moved = this.read(row, tilt) - this.read(row, this.tilt);
    this.level = (this.level ?? 0) + moved;
    for (const block of this.blocks) block.forEach((v, i) => (block[i] = v - moved));
    this.sum.forEach((power, i) => (this.sum[i] = power * 10 ** (-moved / 10)));
    this.offset.set(offset.map((v) => v - moved));
    this.middle = middle - moved;
    this.tilt = tilt;
  }

  /** The floor of every bin in the modem's dB; nothing before the first row. */
  now(): Float32Array | null {
    const level = this.level;
    return level === null ? null : this.offset.map((v) => level + v);
  }

  /**
   * A row as bytes: each bin's dB over its floor. A row of our own transmission (`own`) goes over
   * the floor without its shape, since the audio we play did not pass the receiver's filter. A row
   * before any was fed (the scope opened while we transmit) goes over its own quiet quarter.
   */
  over(row: Float32Array, own = false): Uint8Array {
    const level = this.level ?? quantile(row, LEVEL_QUANTILE);
    return Uint8Array.from(row, (v, i) => byteOfDb(v - level - (own ? this.middle : this.offset[i])));
  }
}

/**
 * For this long after the last row of our own transmission a row still counts as ours, as for the
 * daemon's busy control (AFTER_TX_SEC in neoaprs/mercuryscoping.py): the modem's buffer still holds
 * the frame's end.
 */
export const AFTER_TX_MS = 400;

/**
 * The rows as the painter is given them: a heard row is learnt and told over the floor; a row of
 * our own transmission (or just after it) is told over the floor and not learnt.
 */
export class RowFeed {
  private floor = new Floor();
  private lastOwn = -Infinity;

  /** A row that came at `at` ms: its bytes, and whether it is drawn as our own. */
  take(row: ScopeRow, at: number): { bytes: Uint8Array; tx: boolean } {
    if (row.tx) this.lastOwn = at;
    const tx = row.tx || at - this.lastOwn < AFTER_TX_MS;
    if (!tx) this.floor.feed(row.db);
    return { bytes: this.floor.over(row.db, tx), tx };
  }

  /** Forget the floor and the last transmission. */
  clear(): void {
    [this.floor, this.lastOwn] = [new Floor(), -Infinity];
  }
}
