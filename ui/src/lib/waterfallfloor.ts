// The floor under the HF radio's waterfall (lib/waterfall.ts draws it): the noise each bin of a row has when nothing is on it, found from the rows themselves, so that what is drawn is every bin's dB over its own floor and the
// operator has no gain or zero to set; and the feed that turns the daemon's rows (lib/scoperow.ts, in the modem's dB) into the bytes the painter is given. It is apart from the drawing because it is the half that works on the
// modem's spectra.
import type { ScopeRow } from "@/lib/scoperow";
import { BINS, ROWS_PER_SECOND, byteOfDb, hzOfBin } from "@/lib/waterfall";
import { LIMITS } from "@/protocol/lists";

const { signalLoHz, signalHiHz } = LIMITS.scope;

function quantile(values: ArrayLike<number>, q: number): number {
  const sorted = Float32Array.from(values).sort();
  return sorted[Math.floor(q * (sorted.length - 1))];
}

/** Each value as `pick` of the values up to `half` bins to each side of it, fewer toward the ends so that the window stays even: a filter's skirt, which falls steadily, comes through as it is. */
function windowed(values: Float32Array, half: number, pick: (window: Float32Array) => number): Float32Array {
  return values.map((_, i) => {
    const reach = Math.min(half, i, values.length - 1 - i);
    return pick(values.subarray(i - reach, i + reach + 1));
  });
}

const LEVEL_QUANTILE = 0.25; // the level of a row is read at the bin a quarter up from the quietest, as the daemon's meter reads it...
const LEVEL_CLEAR_HZ = 100; // ...among the bins this far and more from the band of a frame: what the modem's own kind of signal never covers, so that a frame does not lift the level and darken the noise beside itself
const LEVEL_GAIN = 0.1; // the level goes this part of the way to a row's reading (a second or so)...
const LEVEL_SLEW_DB = 0.3; // ...and no more than this in one row: a crash of static or a dropout of a few rows moves it by less than a dB, and a step of 10 dB in the noise is followed in four seconds
const BLOCK_ROWS = ROWS_PER_SECOND; // the shape is learnt from the bins' means over a second...
const SHAPE_BLOCKS = 30; // ...of the last half minute...
const SHAPE_QUANTILE = 0.1; // ...as the third lowest of them: what a bin read while nothing was on it, though frames filled most of the half minute, and though the audio dropped out in a second or two of it
const SHAPE_MEDIAN_HALF = 20; // the shape is a filter's: smooth over 300 Hz. The median over that width does not see a carrier, however long it stays
const SHAPE_SMOOTH_HALF = 4;
const median = (window: ArrayLike<number>): number => quantile(window, 0.5);
const CLEAR_BINS = Array.from({ length: BINS }, (_, i) => i).filter(
  (i) => hzOfBin(i) < signalLoHz - LEVEL_CLEAR_HZ || hzOfBin(i) > signalHiHz + LEVEL_CLEAR_HZ,
);

/** The floor under the waterfall: the noise each bin has when nothing is on it, in the modem's dB, found from the rows themselves. It is the level of the passband now, which follows a change in the noise within seconds, and over
 * that the shape of the passband, bin by bin (a receiver's filter is not flat: its tilt and its skirts would show as lighter and darker stripes), which is learnt slowly. A carrier does not move it, since it is narrower than the shape is
 * smooth; a frame does not, since the level is read beside its band and the shape from the quiet seconds of the half minute; a change that stays is taken in within that half minute. Rows of our own transmission are not fed. */
export class Floor {
  private level: number | null = null;
  private readonly offset = new Float32Array(BINS); // how far each bin's floor stands over the level
  private middle = 0; // the median of them...
  private tilt = new Float32Array(BINS); // ...and each bin's about that middle: taken off a row before its level is read, so that the quiet quarter is the quiet quarter of the noise and not the low end of the filter
  private blocks: Float32Array[] = [];
  private readonly sum = new Float64Array(BINS);
  private count = 0;

  /** The level a row reads: its quiet quarter beside the band of a frame, the shape taken off first. */
  private read(row: Float32Array, tilt: Float32Array): number {
    return quantile(
      CLEAR_BINS.map((i) => row[i] - tilt[i]),
      LEVEL_QUANTILE,
    );
  }

  feed(row: Float32Array): void {
    const reading = this.read(row, this.tilt);
    this.level = this.level === null ? reading : this.level + Math.max(-LEVEL_SLEW_DB, Math.min(LEVEL_SLEW_DB, LEVEL_GAIN * (reading - this.level)));
    for (let i = 0; i < BINS; i++) this.sum[i] += 10 ** ((row[i] - reading) / 10); // (over the row's own reading, not the level that is still on its way to it: a step in the noise is no dip in a bin)
    this.count++;
    // a second's mean of each bin over the readings, with the median across the bins round it: a carrier is gone from it, and it is steady enough that the lowest of thirty is hardly lower than the rest
    const block = windowed(
      Float32Array.from(this.sum, (power) => 10 * Math.log10(power / this.count + 1e-30)),
      SHAPE_MEDIAN_HALF,
      median,
    );
    const full = this.count === BLOCK_ROWS;
    if (!full && this.blocks.length > 0) return;
    if (full) {
      this.blocks = [block, ...this.blocks.slice(0, SHAPE_BLOCKS - 1)];
      this.sum.fill(0);
      this.count = 0;
    }
    this.learn(full ? this.blocks : [block], row); // (in the first second from the rows there are, so that the first row is already drawn over a floor)
  }

  /** The shape from the seconds kept. A new shape changes what a row reads as its level (`row` is the newest): the level, and all that was learnt over the readings, move by as much, so that the floor itself does not jump. */
  private learn(blocks: readonly Float32Array[], row: Float32Array): void {
    const low = Math.floor(SHAPE_QUANTILE * (blocks.length - 1));
    const quiet = Float32Array.from({ length: BINS }, (_, i) => blocks.map((block) => block[i]).sort((a, b) => a - b)[low]);
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

  /** The floor of every bin in the modem's dB; before the first row, nothing. */
  now(): Float32Array | null {
    const level = this.level;
    return level === null ? null : this.offset.map((v) => level + v);
  }

  /** A row as the bytes that are drawn: each bin's dB over its floor. A row of our own transmission (`own`) is told over the floor without its shape: it is the audio we play, which has not been through the receiver's filter.
   * A row that comes before any was fed (the scope opened while we transmit) is told over its own quiet quarter. */
  over(row: Float32Array, own = false): Uint8Array {
    const level = this.level ?? quantile(row, LEVEL_QUANTILE);
    return Uint8Array.from(row, (v, i) => byteOfDb(v - level - (own ? this.middle : this.offset[i])));
  }
}

/** For this long after the last row of our own transmission a row still counts as ours, as the daemon counts it for the busy control (AFTER_TX_SEC of neoaprs/mercuryscoping.py): the modem's buffer still holds the end of our
 * frame and then fills again, and what it tells meanwhile is neither the band's noise nor to be learnt as its floor. */
export const AFTER_TX_MS = 400;

/** The rows of the daemon as the painter is given them: a row heard is learnt by the floor and told over it, a row of our own transmission (and one of the moment after it) is told over the floor and not learnt. */
export class RowFeed {
  private floor = new Floor();
  private lastOwn = -Infinity;

  /** A row that came at `at` milliseconds: its bytes, and whether it is drawn as our own. */
  take(row: ScopeRow, at: number): { bytes: Uint8Array; tx: boolean } {
    if (row.tx) this.lastOwn = at;
    const tx = row.tx || at - this.lastOwn < AFTER_TX_MS;
    if (!tx) this.floor.feed(row.db);
    return { bytes: this.floor.over(row.db, tx), tx };
  }

  /** Forgets the floor and the last transmission: the rows start again. */
  clear(): void {
    [this.floor, this.lastOwn] = [new Floor(), -Infinity];
  }
}
