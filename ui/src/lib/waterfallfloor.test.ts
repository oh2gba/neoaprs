// The floor under the waterfall (lib/waterfallfloor.ts): its behaviour on noise, on a receiver's passband shape, on a step in the noise, on a carrier, on frames and on our own transmission; and the feed of the daemon's rows.
import { describe, expect, it } from "vitest";
import { BINS, ROWS_PER_SECOND, binOfHz, byteOfDb, dbOfByte } from "@/lib/waterfall";
import { AFTER_TX_MS, Floor, RowFeed } from "@/lib/waterfallfloor";

const [BAND_FROM, BAND_TO] = [Math.round(binOfHz(1200)), Math.round(binOfHz(1800))];

/** Numbers from 0 to 1 that are the same at every run. */
function dice(seed: number): () => number {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), a | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** A row of noise as the modem's spectra give it: each bin its own draw about the mean power `level(bin)` dB (two spectra averaged: the mean of two exponential draws). */
function noise(random: () => number, level: (bin: number) => number): Float32Array {
  return Float32Array.from({ length: BINS }, (_, i) => level(i) + 10 * Math.log10((-Math.log(1 - random()) - Math.log(1 - random())) / 2));
}

/** Feeds a floor `seconds` of noise, `signal(bin)` dB of signal power over the noise added where it is given. */
function listen(
  floor: Floor,
  random: () => number,
  seconds: number,
  level: (bin: number) => number,
  signal: (bin: number) => number | null = () => null,
): void {
  for (let row = 0; row < seconds * ROWS_PER_SECOND; row++)
    floor.feed(
      noise(random, (bin) => {
        const over = signal(bin);
        return over === null ? level(bin) : level(bin) + 10 * Math.log10(1 + 10 ** (over / 10));
      }),
    );
}

const mean = (values: ArrayLike<number>, from = 0, to = values.length): number =>
  Array.from(values)
    .slice(from, to)
    .reduce((a, b) => a + b, 0) /
  (to - from);
const floorOf = (floor: Floor): Float32Array => floor.now() ?? new Float32Array(BINS);

describe("the floor", () => {
  const flat = (): number => -40;
  /** A receiver's filter: 6 dB of tilt across the passband, a ripple of 1.5 dB, and a skirt at each end that is 11 dB down at the last bin. */
  const skirt = (bins: number): number => -14 / (1 + Math.exp((bins - 4) / 3));
  const filter = (bin: number): number => -40 - (6 * bin) / BINS + 1.5 * Math.cos((2 * Math.PI * bin) / 120) + skirt(bin) + skirt(BINS - 1 - bin);

  it("is there with the first row, and stands at the noise", () => {
    const [floor, random] = [new Floor(), dice(1)];
    expect(floor.now()).toBeNull();
    listen(floor, random, 0.1, flat);
    expect(Math.abs(mean(floorOf(floor)) + 40)).toBeLessThan(2.5);
    listen(floor, random, 5, flat);
    const now = floorOf(floor);
    expect(Math.abs(mean(now) + 40)).toBeLessThan(1.5);
    expect(Math.max(...now) - Math.min(...now)).toBeLessThan(1.5);
    // the noise over it is spread about 0 dB: the bytes that are drawn
    expect(Math.abs(mean(Array.from(floor.over(noise(random, flat)), dbOfByte)))).toBeLessThan(2.5);
  });

  it("takes the receiver's own passband shape out, bin by bin, skirts and all", () => {
    const [floor, random] = [new Floor(), dice(2)];
    listen(floor, random, 8, filter);
    const error = floorOf(floor).map((v, bin) => v - filter(bin));
    const middle = mean(error);
    expect(Math.abs(middle)).toBeLessThan(1.5);
    expect(Math.max(...Array.from(error, (e) => Math.abs(e - middle)))).toBeLessThan(2.5); // (the skirts, where there are fewest bins to go by)
    expect(Math.max(...Array.from(error.subarray(20, BINS - 20), (e) => Math.abs(e - middle)))).toBeLessThan(0.8);
  });

  it("follows a step in the noise within seconds, up and down, and is not moved by a crash of a few rows", () => {
    const [floor, random] = [new Floor(), dice(3)];
    listen(floor, random, 6, flat);
    const before = mean(floorOf(floor));
    listen(floor, random, 0.3, () => -20); // a crash of static: 20 dB for three rows
    expect(Math.abs(mean(floorOf(floor)) - before)).toBeLessThan(1);
    listen(floor, random, 2, flat);
    listen(floor, random, 1, () => -30); // the noise rises by 10 dB and stays
    expect(mean(floorOf(floor)) - before).toBeGreaterThan(1.5);
    expect(mean(floorOf(floor)) - before).toBeLessThan(4); // (no faster than 3 dB a second)
    listen(floor, random, 5, () => -30);
    expect(Math.abs(mean(floorOf(floor)) - before - 10)).toBeLessThan(1);
    listen(floor, random, 6, flat);
    expect(Math.abs(mean(floorOf(floor)) - before)).toBeLessThan(1);
  });

  it("is not moved by a carrier, however long it sits on its bins", () => {
    const [floor, random] = [new Floor(), dice(4)];
    listen(floor, random, 5, filter);
    const before = floorOf(floor);
    listen(floor, random, 60, filter, (bin) => (bin >= 99 && bin <= 102 ? 30 : null));
    const after = floorOf(floor);
    for (const bin of [95, 99, 100, 102, 106]) expect(Math.abs(after[bin] - before[bin])).toBeLessThan(0.8);
    // and the carrier is still drawn at its strength after that minute
    const row = noise(random, (bin) => filter(bin) + (bin === 100 ? 30 : 0));
    expect(dbOfByte(floor.over(row)[100])).toBeGreaterThan(22);
  });

  it("is not moved by a frame, in its band or beside it, while the frame lasts and after it", () => {
    const [floor, random] = [new Floor(), dice(5)];
    listen(floor, random, 6, filter);
    const before = floorOf(floor);
    const moved = (): number[] => [
      mean(floorOf(floor), BAND_FROM, BAND_TO) - mean(before, BAND_FROM, BAND_TO),
      mean(floorOf(floor), 0, BAND_FROM - 20) - mean(before, 0, BAND_FROM - 20),
    ];
    const frame = (bin: number): number | null => (bin >= BAND_FROM && bin < BAND_TO ? 12 : null);
    listen(floor, random, 3.8, filter, frame);
    for (const shift of moved()) expect(Math.abs(shift)).toBeLessThan(0.8);
    listen(floor, random, 2, filter);
    for (const shift of moved()) expect(Math.abs(shift)).toBeLessThan(0.8);
    // three more frames with two seconds between them: most of the half minute's seconds have a frame in them
    for (let i = 0; i < 3; i++) {
      listen(floor, random, 3.8, filter, frame);
      listen(floor, random, 2, filter);
    }
    for (const shift of moved()) expect(Math.abs(shift)).toBeLessThan(0.8);
  });

  it("takes in a change of the shape that stays, within the half minute", () => {
    const [floor, random] = [new Floor(), dice(6)];
    listen(floor, random, 6, flat);
    const raised = (bin: number): number => (bin >= BAND_FROM && bin < BAND_TO ? -30 : -40);
    listen(floor, random, 10, raised);
    expect(mean(floorOf(floor), BAND_FROM + 10, BAND_TO - 10)).toBeLessThan(-38); // (ten seconds are not yet "stays")
    listen(floor, random, 25, raised);
    expect(Math.abs(mean(floorOf(floor), BAND_FROM + 25, BAND_TO - 25) + 30)).toBeLessThan(1.5);
    expect(Math.abs(mean(floorOf(floor), 0, BAND_FROM - 25) + 40)).toBeLessThan(1.5);
  });

  it("tells a row of our own transmission over the floor without its shape, and a row that comes before any was heard over its own quiet quarter", () => {
    const silent = new Floor();
    expect(Array.from(silent.over(new Float32Array(BINS).fill(-33))).every((byte) => byte === byteOfDb(0))).toBe(true);
    const [floor, random] = [new Floor(), dice(7)];
    listen(floor, random, 8, filter);
    const played = new Float32Array(BINS).fill(-20);
    const own = floor.over(played, true);
    expect(new Set(own).size).toBe(1); // (the audio we play is as flat as it was made)
    expect(Math.abs(dbOfByte(own[0]) - 23)).toBeLessThan(2.5); // (over the passband's middle: -43 dB there)
    const heard = Array.from(floor.over(played), dbOfByte);
    expect(heard[0] - heard[150]).toBeGreaterThan(5); // (as a received row it would stand higher over the skirt's lower floor)
  });
});

describe("the feed of the daemon's rows", () => {
  const row = (db: number, tx = false) => ({ db: new Float32Array(BINS).fill(db), level: -40, tx });

  it("tells a row heard over the floor it learnt, and a row of ours over that floor without learning from it", () => {
    const feed = new RowFeed();
    for (let i = 0; i < 20; i++) expect(feed.take(row(-40), i * 100)).toMatchObject({ tx: false });
    expect(dbOfByte(feed.take(row(-30), 2000).bytes[0])).toBeCloseTo(10, 0);
    const own = feed.take(row(-10, true), 2100);
    expect(own.tx).toBe(true);
    expect(dbOfByte(own.bytes[0])).toBeCloseTo(30, 0);
    expect(dbOfByte(feed.take(row(-40), 2100 + AFTER_TX_MS).bytes[0])).toBeCloseTo(0, 0); // (the floor did not learn our transmission)
  });

  it("counts the rows of the moment after our transmission as ours, and starts again when it is cleared", () => {
    const feed = new RowFeed();
    feed.take(row(-40, true), 1000);
    expect(feed.take(row(-80), 1000 + AFTER_TX_MS - 1).tx).toBe(true); // (the modem's empty buffer: not learnt as the floor)
    expect(feed.take(row(-40), 1000 + AFTER_TX_MS).tx).toBe(false);
    feed.take(row(-40, true), 5000);
    feed.clear();
    expect(feed.take(row(-40), 5100).tx).toBe(false);
    expect(dbOfByte(feed.take(row(-40), 5200).bytes[0])).toBe(0);
  });
});
