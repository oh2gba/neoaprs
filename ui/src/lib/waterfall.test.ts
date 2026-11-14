// The new waterfall's own logic (lib/waterfall.ts, lib/waterfallpainter.ts): the bins of the passband, a line from its rows, the colour table, where a line's bins fall on the pixels, the layout of a box, the ruler's ticks, the time, where a label goes,
// the curve, and the painter on a canvas.
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  BINS,
  BIN_HZ,
  KEPT_LINES,
  LINES_PER_SECOND,
  PACE,
  ROWS_PER_LINE,
  ROWS_PER_SECOND,
  SPECTRA_PER_ROW,
  binOfHz,
  byteOfDb,
  colourTable,
  curveMean,
  curveNow,
  curvePoints,
  dbOfByte,
  hzOfBin,
  keptLines,
  layout,
  lineOf,
  placeLabel,
  plateRect,
  quarterIn,
  rulerTicks,
  scalePosition,
  silentOwn,
  snrText,
  spread,
  timeText,
  xOfHz,
  type Box,
  type Layout,
  type Slot,
  type Speed,
  type Tick,
} from "@/lib/waterfall";
import { LIMITS } from "@/protocol/lists";
import { Waterfall } from "@/lib/waterfallpainter";

const SCALE = [
  [0, 8, 40],
  [8, 52, 190],
  [0, 170, 255],
  [255, 226, 0],
  [255, 40, 16],
] as const;

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

describe("the bins of the passband", () => {
  it("are the modem's own: 307 bins of 7.8 Hz from 300 to 2700 Hz, a row of two spectra each, ten a second by the modem's timer; a line of the picture is two rows, five a second, and two minutes of lines are kept", () => {
    expect(BIN_HZ).toBe(7.8125);
    expect(BINS).toBe(307);
    expect([SPECTRA_PER_ROW, ROWS_PER_SECOND]).toEqual([2, 10]);
    expect([ROWS_PER_LINE, LINES_PER_SECOND, KEPT_LINES]).toEqual([2, 5, 600]);
  });

  it("keep at least as many lines as the tallest picture shows, at any pixel ratio", () => {
    let most = 0;
    for (let ratio = 1; ratio <= 4; ratio += 0.05) for (const width of [320, 380, 560]) most = Math.max(most, layout(width, 378, ratio).rows);
    expect(most).toBeGreaterThan(380);
    expect(most).toBeLessThanOrEqual(KEPT_LINES);
  });

  it("give the bin of a frequency and the frequency of a bin, there and back", () => {
    expect([hzOfBin(0), hzOfBin(BINS - 1)]).toEqual([304.6875, 2695.3125]);
    expect(binOfHz(1500)).toBe(153);
    expect(binOfHz(1503.90625)).toBe(153.5);
    for (const bin of [0, 1, 100, 153, 306]) expect(binOfHz(hzOfBin(bin))).toBe(bin);
    expect(binOfHz(300)).toBeLessThan(0); // (the passband's edges lie half a bin outside the first and the last bin)
    expect(binOfHz(2700)).toBeGreaterThan(BINS - 1);
  });

  it("are told as a byte each: a quarter of a dB to the step from 16 dB under the floor, held at both ends", () => {
    expect([-16, 0, 10, 47.75].map(byteOfDb)).toEqual([0, 64, 104, 255]);
    expect([-80, 300].map(byteOfDb)).toEqual([0, 255]);
    expect([0, 64, 255].map(dbOfByte)).toEqual([-16, 0, 47.75]);
    for (let byte = 0; byte < 256; byte++) expect(byteOfDb(dbOfByte(byte))).toBe(byte);
  });
});

describe("a line of the picture", () => {
  const row = (db: number): Uint8Array => new Uint8Array(BINS).fill(byteOfDb(db));

  it("is the mean of its rows in power, bin by bin, and the row itself where there is one", () => {
    const line = lineOf([row(0), row(10)], false);
    expect(line).toHaveLength(BINS);
    expect(dbOfByte(line[0])).toBeCloseTo(10 * Math.log10((1 + 10) / 2), 0); // (7.4 dB: the mean of the powers, not 5, the mean of the dB)
    expect(new Set(line).size).toBe(1);
    expect(Array.from(lineOf([row(3)], false))).toEqual(Array.from(row(3)));
    const mixed = lineOf([Uint8Array.from({ length: BINS }, (_, i) => (i === 7 ? byteOfDb(30) : byteOfDb(0))), row(0)], false);
    expect([dbOfByte(mixed[6]), dbOfByte(mixed[7])]).toEqual([0, 27]); // (each bin by itself: a carrier in one row of two stands 3 dB lower and beside it nothing moves)
  });

  it("is drawn 24 dB lower when it is of our own transmission, so that our carriers stand where a good station's do and what is beside them is gone", () => {
    expect(dbOfByte(lineOf([row(40), row(40)], true)[0])).toBe(16);
    expect(dbOfByte(lineOf([row(47), row(47)], true)[0])).toBe(23); // (the strongest we play: the scale's yellow, not past its red)
    expect(lineOf([row(12), row(12)], true)[0]).toBe(byteOfDb(-12)); // (the streaks beside our signal: under the ground's -10 dB)
    expect(lineOf([row(0)], true)[0]).toBe(0);
  });

  it("is not made of a row of our own transmission that has nothing of ours in it", () => {
    expect(silentOwn(row(-16))).toBe(true); // (the modem's empty buffer)
    expect(silentOwn(row(-4))).toBe(true); // (the buffer filling again: under the noise)
    expect(silentOwn(row(6))).toBe(true); // (keyed, and the audio has not begun: the band's own noise at most)
    const begun = row(0);
    begun[150] = byteOfDb(35);
    expect(silentOwn(begun)).toBe(false);
  });
});

describe("the colour table", () => {
  const luminance = (table: Uint8ClampedArray, byte: number): number => 0.2126 * table[byte * 4] + 0.7152 * table[byte * 4 + 1] + 0.0722 * table[byte * 4 + 2];
  const colour = (table: Uint8ClampedArray, byte: number): number[] => Array.from(table.subarray(byte * 4, byte * 4 + 4));
  const table = colourTable(SCALE);

  it("has 256 opaque colours, the scale's first at the weak end and its last at the strong end", () => {
    expect(table).toHaveLength(1024);
    for (let byte = 0; byte < 256; byte++) expect(table[byte * 4 + 3]).toBe(255);
    expect(colour(table, 0)).toEqual([0, 8, 40, 255]);
    expect(colour(table, byteOfDb(-10))).toEqual([0, 8, 40, 255]);
    expect(colour(table, 255)).toEqual([255, 40, 16, 255]);
    expect(colour(table, byteOfDb(33))).toEqual([255, 40, 16, 255]);
    expect(colourTable([])).toHaveLength(1024);
  });

  it("never goes back along the scale for a stronger bin, and grows lighter all the way from the ground to cyan", () => {
    expect([-30, -10, 8, 14, 23, 33, 90].map(scalePosition)).toEqual([0, 0, 1, 2, 3, 4, 4]);
    for (let db = -20; db < 50; db += 0.25) expect(scalePosition(db + 0.25)).toBeGreaterThanOrEqual(scalePosition(db));
    for (let byte = 0; byte < byteOfDb(14); byte++) expect(luminance(table, byte + 1)).toBeGreaterThanOrEqual(luminance(table, byte) - 0.01);
  });

  it("makes the noise of a line a dark grain: many shades, none of them the ground alone, all darker than the scale's blue", () => {
    const shades = new Set<string>();
    for (let db = -6; db <= 4; db += 0.25) shades.add(colour(table, byteOfDb(db)).join(","));
    expect(shades.size).toBeGreaterThan(30);
    expect(luminance(table, byteOfDb(0))).toBeGreaterThan(1.5 * luminance(table, 0)); // (the middle of the noise is not the ground: not black)
    expect(luminance(table, byteOfDb(4))).toBeLessThan(luminance(table, byteOfDb(8)));
    expect(scalePosition(0)).toBeLessThan(0.2); // (and dark: a sixth of the way to the blue)
    expect(scalePosition(4)).toBeLessThan(0.5); // (its brightest specks are not half way there)
  });

  it("shows a frame the modem can just read, 7 to 9 dB over the floor, far lighter than the noise, and what is 6 dB over the floor lighter than all but a speck of it", () => {
    const noisy = luminance(table, byteOfDb(0));
    expect(luminance(table, byteOfDb(6))).toBeGreaterThan(2 * noisy);
    expect(luminance(table, byteOfDb(8))).toBeGreaterThan(3 * noisy);
    expect(luminance(table, byteOfDb(6))).toBeGreaterThan(1.3 * luminance(table, byteOfDb(4))); // (4 dB: the brightest specks of the noise)
  });

  it("spends its colours on what is heard: a good station's frame is cyan, its strongest bins and a strong station green to yellow, and the red is left for a signal 33 dB over the noise", () => {
    expect(colour(table, byteOfDb(14))).toEqual([0, 170, 255, 255]); // (a frame at an SNR of 6 stands 14 dB over the floor)
    expect(scalePosition(24)).toBeGreaterThan(3); // (its strongest bins: past the yellow)
    expect(scalePosition(9)).toBeGreaterThan(1); // (a frame at an SNR of 0: past the blue)
    expect(colour(table, byteOfDb(23))).toEqual([255, 226, 0, 255]);
    expect(colour(table, byteOfDb(32))).not.toEqual([255, 40, 16, 255]);
  });

  it("goes from cyan to yellow through green, as on a rig, and not through grey", () => {
    const [r, g, b] = colour(table, byteOfDb(18.5));
    expect(g).toBeGreaterThan(200);
    expect(Math.max(r, b)).toBeLessThan(120);
  });
});

describe("the pixels of a line", () => {
  const counted = Float32Array.from({ length: BINS }, (_, bin) => bin);

  it("are part of the way between two bins where a bin is wider than a pixel and narrower than two", () => {
    const width = 560; // the card over the map on a plain screen: 1.8 pixels to the bin
    const out = spread(counted, width);
    expect(out).toHaveLength(width);
    expect([out[0], out[width - 1]]).toEqual([0, BINS - 1]); // (the edges of the passband lie outside the first and the last bin: held)
    for (let x = 1; x < out.length; x++) expect(out[x]).toBeGreaterThanOrEqual(out[x - 1]);
    expect(out[280] % 1).not.toBe(0);
    expect(out[280]).toBeCloseTo(binOfHz(300 + (280.5 / width) * 2400), 3);
  });

  it("are the nearest bin where a bin is two pixels wide and more: a crisp cell on a screen of two or three pixels to the CSS pixel, not a smear", () => {
    for (const width of [1120, 1029, 1680]) {
      const out = spread(counted, width);
      expect(out.every((value) => value % 1 === 0)).toBe(true);
      expect([out[0], out[width - 1]]).toEqual([0, BINS - 1]);
      const widths = Array.from({ length: BINS }, (_, bin) => out.filter((value) => value === bin).length).slice(1, -1); // (the first and the last bin lie half outside the passband)
      expect(Math.max(...widths) - Math.min(...widths)).toBeLessThanOrEqual(1); // (every bin as wide as the next, to the pixel)
      expect(Math.min(...widths)).toBeGreaterThanOrEqual(Math.floor(width / 307.2));
    }
  });

  it("are the strongest of the bins they cover where the box is narrower, so that a carrier one bin wide is not lost", () => {
    const carrier = new Uint8Array(BINS);
    carrier[150] = 200;
    const out = spread(carrier, 100);
    expect(Math.max(...out)).toBe(200);
    expect(out.filter((v) => v === 200).length).toBeLessThanOrEqual(2);
    expect(out[0]).toBe(0);
  });
});

describe("the layout of a box", () => {
  const SIZES = [
    [420, 240],
    [560, 380],
    [343, 260],
  ] as const;
  const bottom = (box: Box): number => box.y + box.h;

  it.each(SIZES)(
    "puts the ruler over the picture over the curve in %i by %i, nothing over another and nothing without a size, on any screen",
    (width, height) => {
      for (const ratio of [1, 1.25, 1.5, 2, 3]) {
        const l: Layout = layout(width, height, ratio);
        expect([l.width, l.height]).toEqual([Math.round(width * ratio), Math.round(height * ratio)]);
        for (const box of [l.ruler, l.picture, l.curve]) {
          expect(box.w).toBe(l.width);
          expect(box.x).toBe(0);
          expect(box.h).toBeGreaterThan(0);
        }
        expect(l.ruler.y).toBe(0);
        expect(l.picture.y).toBe(bottom(l.ruler));
        expect(l.curve.y).toBeGreaterThan(bottom(l.picture)); // (the rule between them)
        expect(bottom(l.curve)).toBe(l.height);
        expect(l.rowPx).toBe(Math.max(1, Math.round(ratio)));
        expect(l.picture.h).toBe(l.rows * l.rowPx);
        expect(l.picture.h).toBeGreaterThan(l.curve.h); // (the waterfall is the main thing)
        expect(l.plate).toBeGreaterThan(l.text);
        expect(l.gutter).toBeLessThan(xOfHz(1200, l.width)); // (the times at the left edge end before the band of a frame)
      }
    },
  );

  it("gives the box in Settings 169 lines of waterfall, thirty-four seconds and more, and the card over the map 281, with the curve a fifth of the box and no text smaller than the page's smallest", () => {
    expect(layout(420, 240)).toMatchObject({
      ruler: { y: 0, h: 22 },
      picture: { y: 22, h: 169 },
      curve: { y: 192, h: 48 },
      rows: 169,
      rowPx: 1,
      unit: 1,
      text: 11,
      plate: 16,
      gutter: 64,
    });
    expect(layout(420, 240).rows / LINES_PER_SECOND).toBeGreaterThan(33); // (at the timer's five lines a second; forty seconds as the spectra really come)
    expect(layout(560, 380)).toMatchObject({ picture: { y: 22, h: 281 }, curve: { y: 304, h: 76 }, rows: 281 });
    expect(layout(343, 260, 3)).toMatchObject({ width: 1029, height: 780, rowPx: 3, rows: 185, picture: { h: 555 }, text: 33 });
  });

  it("still has a size for everything in a box too small to be of use", () => {
    const l = layout(40, 20);
    for (const box of [l.ruler, l.picture, l.curve]) expect(box.h).toBeGreaterThan(0);
    expect(l.rows).toBeGreaterThan(0);
  });
});

describe("the ruler", () => {
  it("has a tick every 100 Hz from 300 to 2700 and a number every 500", () => {
    const ticks: Tick[] = rulerTicks(420, 40);
    expect(ticks.map((tick) => tick.hz)).toEqual(Array.from({ length: 25 }, (_, i) => 300 + 100 * i));
    expect(ticks.filter((tick) => tick.numbered).map((tick) => [tick.hz, tick.x])).toEqual([
      [500, 35],
      [1000, 123],
      [1500, 210],
      [2000, 298],
      [2500, 385],
    ]);
    expect([ticks[0].x, ticks[24].x]).toEqual([0, 419]); // (the last tick is on the last pixel, not past it)
    for (let i = 1; i < ticks.length; i++) expect(ticks[i].x).toBeGreaterThan(ticks[i - 1].x);
  });

  it("numbers every 1000 where the numbers would touch", () => {
    expect(
      rulerTicks(150, 40)
        .filter((tick) => tick.numbered)
        .map((tick) => tick.hz),
    ).toEqual([1000, 2000]);
    expect(rulerTicks(343, 40).filter((tick) => tick.numbered)).toHaveLength(5); // (a phone still has all five)
  });

  it("puts a frequency where it is across the box: the band of a frame from 1200 to 1800 Hz", () => {
    expect([300, 1200, 1500, 1800, 2700].map((hz) => xOfHz(hz, 560))).toEqual([0, 210, 280, 350, 560]);
  });
});

describe("the time", () => {
  it("is written in the viewer's time, hh:mm:ss, as the page writes the time of a packet, on the first line of every quarter of a minute", () => {
    expect(timeText(new Date(2026, 10, 13, 9, 5, 7).getTime())).toBe("09:05:07");
    expect(timeText(new Date(2026, 10, 13, 23, 59, 45, 900).getTime())).toBe("23:59:45");
    expect(quarterIn(15_000, 200)).toBe(15_000); // (the line from 15.0 to 15.2 s holds the quarter)
    expect(quarterIn(14_800, 200)).toBeNull();
    expect(quarterIn(15_200, 200)).toBeNull();
    expect(quarterIn(30_000, 200)).toBe(30_000);
  });

  it("is written at the Slow speed on the line of two fifths of a second that holds the quarter, as the quarter's own time", () => {
    const noon = new Date(2026, 10, 13, 12, 0, 0).getTime();
    expect(quarterIn(noon + 14_800, 400)).toBe(noon + 15_000); // (15 000 / 400 is 37.5: every other quarter falls in the middle of a line)
    expect(timeText(quarterIn(noon + 14_800, 400) ?? 0)).toBe("12:00:15");
    expect(quarterIn(noon + 14_400, 400)).toBeNull();
    expect(quarterIn(noon + 15_200, 400)).toBeNull();
    expect(quarterIn(noon + 30_000, 400)).toBe(noon + 30_000);
    expect(quarterIn(noon + 29_600, 400)).toBeNull();
  });

  it("writes the SNR of what was heard beside its call in whole dB, with a minus sign", () => {
    expect([-3.4, -0.4, 0, 9.6].map(snrText)).toEqual(["\u22123", "0", "0", "10"]);
  });
});

describe("the speeds of the monitor card", () => {
  it("are lines of two fifths of a second at Slow, today's lines at Normal, and today's lines twice as high at Fast; two minutes of each are kept", () => {
    expect(PACE).toEqual({ slow: { lineMs: 400, tall: 1 }, normal: { lineMs: 200, tall: 1 }, fast: { lineMs: 200, tall: 2 } });
    expect(PACE.normal.lineMs).toBe(1000 / LINES_PER_SECOND);
    expect([keptLines(PACE.slow.lineMs), keptLines(PACE.normal.lineMs), keptLines(PACE.fast.lineMs)]).toEqual([300, 600, 600]);
    expect(keptLines(PACE.normal.lineMs)).toBe(KEPT_LINES);
  });
});

describe("the label of what was heard", () => {
  const overlap = (a: Slot, b: Slot, l: Layout): boolean => Math.abs(a.row - b.row) * l.rowPx < l.plate && a.x < b.x + b.w && b.x < a.x + a.w;

  it("stands beside the band of a frame on the line the frame ended: right of it, then left of it, then against the right edge, then lower", () => {
    const l = layout(560, 380);
    const taken: Slot[] = [];
    const place = (row: number, w: number): Slot | null => {
      const slot = placeLabel(row, w, taken, l);
      if (slot) taken.push(slot);
      return slot;
    };
    expect(place(100, 90)).toEqual({ row: 100, x: 354, w: 90 }); // (four pixels right of 1800 Hz)
    expect(place(100, 90)).toEqual({ row: 100, x: 116, w: 90 }); // (ending four pixels left of 1200 Hz)
    expect(place(100, 90)).toEqual({ row: 100, x: 466, w: 90 });
    expect(place(100, 90)).toEqual({ row: 83, x: 354, w: 90 }); // (seventeen lines down: a label's room and a pixel of air)
    expect(place(119, 90)).toEqual({ row: 119, x: 354, w: 90 }); // (the next frame, 3.8 s later, has the place beside the band to itself)
  });

  it("puts a label left of the band where the right is taken, and never lets one cross the right edge", () => {
    const l = layout(560, 380);
    const right = xOfHz(1800, l.width) + 4;
    const room = l.width - 4 - right;
    expect(placeLabel(50, room, [], l)?.x).toBe(right); // (it just fits)
    const first = placeLabel(50, 80, [], l);
    expect(placeLabel(50, 80, first ? [first] : [], l)).toEqual({ row: 50, x: xOfHz(1200, l.width) - 4 - 80, w: 80 }); // (right is taken: to the left of the band)
    const wide = room + 1; // (a pixel too wide for the right, and the left has less room for it still: it ends at the edge, against the band if it must)
    expect(placeLabel(50, wide, [], l)).toEqual({ row: 50, x: l.width - 4 - wide, w: wide });
    for (const w of [20, 80, 120, 200, 300, 400]) {
      const slot = placeLabel(50, w, [], l);
      expect(slot && slot.x + slot.w <= l.width - 4).toBe(true);
    }
  });

  it("has a plate of the label's width, the text's height and a pixel above and below, round the line its text is written on", () => {
    for (const ratio of [1, 2, 3]) {
      const l = layout(560, 380, ratio);
      expect(plateRect({ row: 5, x: 357 * ratio, w: 78 * ratio }, 31 * ratio, l)).toEqual({
        x: 357 * ratio,
        y: 31 * ratio - Math.round((13 * ratio) / 2),
        w: 78 * ratio,
        h: 13 * ratio,
      });
    }
  });

  it("keeps out of the times at the left edge where the box is narrow", () => {
    const l = layout(343, 260);
    const first = placeLabel(50, 100, [], l);
    expect(first).toEqual({ row: 50, x: 218, w: 100 });
    const second = placeLabel(50, 100, first ? [first] : [], l); // (left of the band it would run into the times: it goes under the first)
    expect(second).toEqual({ row: 33, x: 218, w: 100 });
    expect(placeLabel(50, 330, [], l)?.x).toBe(l.gutter); // (a label wider than the box has room for still starts after the times)
  });

  it("is never written over another label, and is left out where every place is taken", () => {
    for (const [width, height, ratio] of [
      [420, 240, 1],
      [560, 380, 2],
      [343, 260, 3],
    ] as const) {
      const l = layout(width, height, ratio);
      const taken: Slot[] = [];
      let left = 0;
      const random = dice(width);
      for (let i = 0; i < 60; i++) {
        const slot = placeLabel(1000 + Math.floor(i / 4) * 5, Math.round((60 + 60 * random()) * ratio), taken, l);
        if (slot) taken.push(slot);
        else left++;
      }
      expect(taken.length).toBeGreaterThan(5);
      expect(left).toBeGreaterThan(0);
      for (const a of taken) {
        expect(a.x).toBeGreaterThanOrEqual(l.gutter);
        for (const b of taken) if (a !== b) expect(overlap(a, b, l)).toBe(false);
      }
    }
  });
});

describe("the points of the curve's line", () => {
  it("has one point at the centre of every bin and the first and the last carried to the edges", () => {
    const ys = Float32Array.from({ length: BINS }, (_, i) => 100 - i);
    for (const width of [343, 872, 1072]) {
      const points = curvePoints(ys, width);
      expect(points).toHaveLength(BINS + 2);
      expect(points[0]).toEqual({ x: 0, y: 100 });
      expect(points.at(-1)).toEqual({ x: width, y: 100 - (BINS - 1) });
      const centres = points.slice(1, -1);
      centres.forEach((point, i) => {
        expect(point.y).toBe(100 - i);
        expect(point.x).toBeCloseTo(((hzOfBin(i) - LIMITS.scope.loHz) / (LIMITS.scope.hiHz - LIMITS.scope.loHz)) * width, 6);
        if (i > 0) expect(point.x - centres[i - 1].x).toBeCloseTo(centres[1].x - centres[0].x, 6); // (evenly)
      });
      expect(centres[0].x).toBeGreaterThan(0);
      expect(centres.at(-1)?.x).toBeLessThan(width);
    }
    expect(curvePoints([], 100)).toEqual([]);
  });
});

describe("the curve", () => {
  const kept = (db: number, tx = false): { bytes: Uint8Array; tx: boolean } => ({ bytes: new Uint8Array(BINS).fill(byteOfDb(db)), tx });
  const meanDb = (lines: { bytes: Uint8Array; tx: boolean }[]): number => dbOfByte(curveMean(lines)[0]);
  const nowDb = (lines: { bytes: Uint8Array; tx: boolean }[]): number => dbOfByte(curveNow(lines)[0]);

  it("has as its quiet shape the mean in dB of the last two seconds of lines, and of no older one", () => {
    const quiet = Array.from({ length: 2 * LINES_PER_SECOND - 1 }, () => kept(0));
    expect(curveMean([kept(10), ...quiet])).toHaveLength(BINS);
    expect(meanDb([kept(10), ...quiet, kept(40), kept(40)])).toBeCloseTo(10 / (2 * LINES_PER_SECOND));
    expect(meanDb([kept(8)])).toBe(8);
    expect(meanDb([])).toBe(dbOfByte(0)); // (nothing kept yet: nothing to divide by, and no throw)
  });

  it("has as its bright line the mean in power of the last second of lines: over noise it lies on the floor, and a frame is in it at once", () => {
    const quiet = Array.from({ length: LINES_PER_SECOND - 1 }, () => kept(0));
    expect(curveNow([kept(0), ...quiet])).toHaveLength(BINS);
    expect(nowDb([kept(10), ...quiet, kept(40)])).toBeCloseTo(10 * Math.log10((10 + LINES_PER_SECOND - 1) / LINES_PER_SECOND), 5); // (4.5 dB with the first line of a frame, where the mean of the dB would say 2)
    expect(nowDb([kept(8)])).toBe(8);
    expect(nowDb([])).toBe(dbOfByte(0));
    // noise of lines (four spectra each) is level within a few dB in the bright line, where one line alone is spread over 7 dB
    const random = dice(8);
    const noise = (): { bytes: Uint8Array; tx: boolean } => ({
      bytes: Uint8Array.from({ length: BINS }, () =>
        byteOfDb(10 * Math.log10(-(Math.log(1 - random()) + Math.log(1 - random()) + Math.log(1 - random()) + Math.log(1 - random())) / 4)),
      ),
      tx: false,
    });
    const lines = Array.from({ length: LINES_PER_SECOND }, noise);
    const spreadOf = (bytes: ArrayLike<number>): number => {
      const sorted = Array.from(bytes, dbOfByte).sort((a, b) => a - b);
      return sorted[Math.floor(0.95 * BINS)] - sorted[Math.floor(0.05 * BINS)];
    };
    expect(spreadOf(curveNow(lines))).toBeLessThan(0.6 * spreadOf(lines[0].bytes));
    expect(Math.abs(Array.from(curveNow(lines), dbOfByte).reduce((a, b) => a + b, 0) / BINS)).toBeLessThan(0.5);
  });

  it("leaves our own transmission out of what is heard after it, and what was heard out of our transmission, in the shape and in the line", () => {
    for (const curve of [meanDb, nowDb]) {
      expect(curve([kept(0), kept(0), kept(16, true), kept(16, true), kept(0)])).toBe(0);
      expect(curve([kept(16, true), kept(0), kept(0), kept(0)])).toBe(16);
      expect(curve([kept(4), kept(16, true), kept(4), kept(4)])).toBe(4); // (not the lines from before the transmission either: they are older than it)
    }
  });
});

interface Fake {
  canvas: HTMLCanvasElement;
  calls: string[];
  strips: { y: number; width: number; height: number; data: number[] }[];
  resize: (width: number, height: number) => void;
}

/** A canvas with the tokens on it whose context writes down what is drawn; `resize` gives it another room. */
function fakeCanvas(width: number, height: number): Fake {
  const calls: string[] = [];
  const strips: Fake["strips"] = [];
  const size = { width, height };
  const special: Record<string, (...args: never[]) => unknown> = {
    createImageData: (w: number, h: number) => ({ width: w, height: h, data: new Uint8ClampedArray(w * h * 4) }),
    measureText: (text: string) => ({ width: text.length * 6 }),
    putImageData: (image: ImageData, x: number, y: number, ...dirty: number[]) => {
      strips.push({ y, width: image.width, height: image.height, data: Array.from(image.data.subarray(0, 8)) });
      calls.push(`putImageData(${[`${image.width}x${image.height}`, x, y, ...dirty].join(",")})`);
    },
    drawImage: (image: unknown, ...args: number[]) => calls.push(`drawImage(${image === canvas ? "itself" : "other"},${args.join(",")})`),
  };
  const context = new Proxy(
    {},
    {
      get: (_target, name: string) => special[name] ?? ((...args: unknown[]) => calls.push(`${name}(${args.join(",")})`)),
      set: (_target, name: string, value: unknown) => {
        calls.push(`${name}=${String(value)}`);
        return true;
      },
    },
  );
  const canvas = document.createElement("canvas");
  Object.defineProperty(canvas, "clientWidth", { get: () => size.width });
  Object.defineProperty(canvas, "clientHeight", { get: () => size.height });
  SCALE.forEach((c, i) => canvas.style.setProperty(`--waterfall-${i}`, "#" + c.map((v) => v.toString(16).padStart(2, "0")).join("")));
  for (const [name, value] of Object.entries({ rule: "rule", ink: "ink", grid: "grid", rx: "receive", tx: "transmit" }))
    canvas.style.setProperty(`--waterfall-${name}`, value);
  document.body.append(canvas);
  vi.spyOn(canvas, "getContext").mockReturnValue(context as unknown as CanvasRenderingContext2D);
  return { canvas, calls, strips, resize: (w, h) => Object.assign(size, { width: w, height: h }) };
}

describe("the painter", () => {
  const START = new Date(2026, 10, 13, 12, 0, 0).getTime();
  const row = (db: number): Uint8Array => new Uint8Array(BINS).fill(byteOfDb(db));
  const drawn = (calls: string[], name: string): string[] => calls.filter((call) => call.startsWith(`${name}(`));
  const texts = (calls: string[]): string[] => drawn(calls, "fillText").map((call) => call.slice("fillText(".length).split(",")[0]);
  const colourOf = (db: number): number[] => Array.from(colourTable(SCALE).subarray(byteOfDb(db) * 4, byteOfDb(db) * 4 + 4));
  const GROUND = colourOf(-16); // (the scale's first colour: a line with nothing in it)
  /** The two rows of a line, the first at `at` (the line's own moment): it is whole when a row of a later line comes. */
  const line = (painter: Waterfall, db: number, at: number, tx = false): void => {
    for (const ms of [0, 100]) painter.push(row(db), at + ms, tx);
  };

  afterEach(() => {
    document.body.replaceChildren();
    vi.unstubAllGlobals();
  });

  it("makes the canvas as many pixels as its room on the screen and draws the ruler and the curve's grid with the first row, and the first line when it is whole", () => {
    vi.stubGlobal("devicePixelRatio", 2);
    const { canvas, calls, strips } = fakeCanvas(420, 240);
    const painter = new Waterfall(canvas);
    painter.push(row(60), START, false);
    expect([canvas.width, canvas.height]).toEqual([840, 480]);
    expect(calls).toContain("fillStyle=#000828"); // (the ground: the first colour of the scale)
    expect(texts(calls)).toEqual(["500", "1000", "1500", "2000", "2500"]);
    expect(calls).toContain(`fillRect(${xOfHz(1200, 840)},40,${xOfHz(1800, 840) - xOfHz(1200, 840)},4)`); // (the bracket of the band of a frame, on the ruler's lower edge)
    expect(calls[calls.indexOf(`fillRect(${xOfHz(1200, 840)},40,${xOfHz(1800, 840) - xOfHz(1200, 840)},4)`) - 1]).toBe("fillStyle=receive");
    expect(calls).toContain("setLineDash(2,6)"); // (the grid's dotted lines: a CSS pixel of line to three of none)
    painter.push(row(60), START + 100, false);
    expect(strips).toEqual([]); // (the fifth of a second is not over: no line yet)
    painter.push(row(60), START + 200, false);
    expect(strips).toEqual([{ y: 44, width: 840, height: 2, data: [255, 40, 16, 255, 255, 40, 16, 255] }]); // (one line of two pixels' height, under the ruler, in the scale's last colour)
  });

  it("draws the curve's bright line one CSS pixel thick on a screen of three pixels to the CSS pixel, where what it tells is in the box and where it is under it", () => {
    vi.stubGlobal("devicePixelRatio", 3);
    const { canvas, calls } = fakeCanvas(343, 260);
    const { curve, width, unit } = layout(343, 260, 3);
    const painter = new Waterfall(canvas);
    painter.push(row(-16), START + 1000, false);
    calls.length = 0; // (the empty box is drawn with the first row; the line comes when it is whole)
    painter.push(row(-16), START + 1200, false);
    expect(unit).toBe(3);
    const half = unit / 2;
    const bottom = curve.y + curve.h - unit + half; // (the lowest line of the box, through the middle of its pixels)
    expect(drawn(calls, "lineTo").filter((call) => call.endsWith(`,${bottom})`))).toHaveLength(2 * (BINS + 2) - 1); // (the shape and the bright line, a point to each bin and one to each edge, the line's first is a moveTo: the modem's silence is not drawn off the box)
    expect(drawn(calls, "rect")).toEqual([]); // (no column to the pixel: a line through the points)
    expect(calls).toContain(`lineWidth=${unit}`);
    expect(calls).toContain("lineJoin=round");
    expect(drawn(calls, "stroke")).toHaveLength(2); // (the grid's one path of dashes and the bright line)
    painter.clear();
    calls.length = 0;
    line(painter, 12, START + 2000);
    painter.push(row(12), START + 2200, false);
    const [, top] = drawn(calls, "lineTo").at(-2)?.slice("lineTo(".length, -1).split(",").map(Number) ?? [];
    expect(top).toBe(curve.y + Math.round(0.5 * (curve.h - unit)) + half); // (12 dB over the floor is the middle of a box from -8 to 32 dB)
    expect(calls).toContain(`fillRect(0,${curve.y + Math.round(0.8 * (curve.h - unit))},${width},${unit})`); // (the floor's line, a fifth of the way up)
    expect(drawn(calls, "stroke")).toHaveLength(2); // (the whole grid is one path of dashes, and the bright line one more)
    expect(calls.filter((call) => call === "setLineDash()")).toHaveLength(1);
  });

  it("moves what is there down by a copy of the canvas onto itself and writes only the new line as pixels", () => {
    const { canvas, calls, strips } = fakeCanvas(420, 240);
    const painter = new Waterfall(canvas);
    line(painter, 0, START);
    painter.push(row(-16), START + 200, false);
    calls.length = 0;
    strips.length = 0;
    painter.push(row(-16), START + 300, false);
    expect(calls).toEqual([]); // (a row of the line under way: nothing is drawn for it)
    painter.push(row(-16), START + 400, false);
    expect(drawn(calls, "drawImage")).toEqual(["drawImage(itself,0,22,420,168,0,23,420,168)"]);
    expect(strips).toEqual([{ y: 22, width: 420, height: 1, data: [0, 8, 40, 255, 0, 8, 40, 255] }]);
    expect(calls.indexOf("drawImage(itself,0,22,420,168,0,23,420,168)")).toBeLessThan(calls.indexOf("putImageData(420x1,0,22)"));
    expect(texts(calls)).toEqual([]); // (the ruler stands: it is not drawn again for a line)
  });

  it("puts a row on the line of its moment: a fifth of a second that no row came in is the line before it again, and longer without rows is a gap of the ground", () => {
    const { canvas, calls, strips } = fakeCanvas(420, 240);
    const painter = new Waterfall(canvas);
    line(painter, 8, START);
    painter.push(row(0), START + 400, false); // (nothing came from 200 to 400 ms)
    expect(strips.map((strip) => strip.data.slice(0, 4))).toEqual([colourOf(8), colourOf(8)]);
    expect(drawn(calls, "drawImage").at(-1)).toBe("drawImage(itself,0,22,420,167,0,24,420,167)"); // (moved down two lines at once)
    strips.length = 0;
    painter.push(row(0), START + 3400, false); // (the modem away for three seconds)
    expect(strips).toHaveLength(15);
    expect(strips.map((strip) => strip.data.slice(0, 4))).toEqual([
      ...Array.from({ length: 3 }, () => colourOf(0)),
      ...Array.from({ length: 12 }, () => GROUND),
    ]); // (the line of the row at 0.4 s, held twice, and then the ground)
  });

  it("marks our own transmission along the left edge and on the ruler's bracket, in the colour of transmit, and draws it 24 dB lower", () => {
    const { canvas, calls, strips } = fakeCanvas(420, 240);
    const painter = new Waterfall(canvas);
    line(painter, 0, START);
    calls.length = 0;
    strips.length = 0;
    painter.push(row(40), START + 200, true);
    expect(calls[calls.indexOf("fillRect(158,20,105,2)") - 1]).toBe("fillStyle=transmit"); // (the bracket at once, with the first row of ours)
    expect(strips.map((strip) => strip.data.slice(0, 4))).toEqual([colourOf(0)]);
    expect(calls).not.toContain("fillRect(0,22,3,1)");
    painter.push(row(40), START + 300, true);
    painter.push(row(40), START + 400, true);
    expect(calls).toContain("fillRect(0,22,3,1)");
    expect(calls[calls.indexOf("fillRect(0,22,3,1)") - 1]).toBe("fillStyle=transmit");
    expect(strips.map((strip) => strip.data.slice(0, 4))).toEqual([colourOf(0), colourOf(16)]);
    calls.length = 0;
    line(painter, 0, START + 600);
    expect(calls[calls.indexOf("fillRect(158,20,105,2)") - 1]).toBe("fillStyle=receive");
    calls.length = 0;
    painter.push(row(0), START + 800, false);
    expect(calls).not.toContain("fillRect(0,22,3,1)");
  });

  it("never makes a line of both what is heard and our own transmission, and draws a row of ours with nothing in it as the ground with the mark of ours", () => {
    const { canvas, calls, strips } = fakeCanvas(420, 240);
    const painter = new Waterfall(canvas);
    line(painter, 0, START);
    strips.length = 0;
    painter.push(row(4), START + 200, false);
    painter.push(row(-16), START + 300, true); // keyed in the middle of a line, and the audio has not begun: the line is ours, and the row heard before in it is let go
    painter.push(row(-16), START + 400, true);
    expect(strips.map((strip) => strip.data.slice(0, 4))).toEqual([colourOf(0), GROUND]);
    painter.push(row(40), START + 600, true);
    painter.push(row(40), START + 700, true);
    painter.push(row(-16), START + 800, true); // the modem's buffer is empty
    painter.push(row(0), START + 900, false);
    painter.push(row(0), START + 1000, false);
    expect(strips.map((strip) => strip.data.slice(0, 4))).toEqual([colourOf(0), GROUND, GROUND, colourOf(16), colourOf(0)]);
    expect(calls.filter((call) => call === "fillRect(0,22,3,1)")).toHaveLength(3); // (the three lines of ours have the strip, the last one heard has not)
  });

  it("draws a line across with the time under it at the left edge on the first line of a quarter of a minute, and writes what was heard beside the band on the line of its moment, letters with a dark edge, and a plate behind a call", () => {
    const { canvas, calls } = fakeCanvas(560, 380);
    const painter = new Waterfall(canvas);
    for (let i = 0; i <= 152; i++) {
      if (i >= 148) calls.length = 0;
      painter.push(row(0), START + i * 100, false);
      if (i >= 148) expect(texts(calls)).toEqual(i === 152 ? ["12:00:15"] : []); // (the line of 15.0 to 15.2 s, whole when the row at 15.2 s comes)
    }
    expect(calls[calls.indexOf("fillRect(0,22,560,1)") - 1]).toBe("fillStyle=grid");
    expect(calls).toContain("fillText(12:00:15,8,32)");
    expect(calls.indexOf("strokeText(12:00:15,8,32)")).toBeLessThan(calls.indexOf("fillText(12:00:15,8,32)"));
    expect(calls).toContain("strokeStyle=#000828"); // (the dark edge is the ground's colour)
    expect(calls).toContain("globalAlpha=0.7"); // (the time is fainter than a call)
    calls.length = 0;
    painter.label("Q1ABC −3 dB", START + 15_100);
    painter.label("Q1DEF 10 dB", START + 15_000);
    expect(drawn(calls, "fillText")).toEqual(["fillText(Q1ABC −3 dB,357,31)", `fillText(Q1DEF 10 dB,${210 - 4 - 72 + 3},31)`]);
    expect(drawn(calls, "strokeText")).toHaveLength(2);
    expect(calls).toContain("fillStyle=ink");
    expect(drawn(calls, "clip")).toHaveLength(2); // (a label ends where the picture does)
    expect(drawn(calls, "roundRect")).toEqual(["roundRect(354,24,72,13,2)", "roundRect(134,24,72,13,2)"]); // (a plate of the text's width (6 pixels a letter here) and three pixels of air, drawn at 70 % in the ground's colour before the letters)
    expect(drawn(calls, "fillRect")).toEqual([]);
    expect(calls.slice(calls.indexOf("roundRect(354,24,72,13,2)") - 3, calls.indexOf("roundRect(354,24,72,13,2)"))).toEqual([
      "globalAlpha=0.7",
      "fillStyle=#000828",
      "beginPath()",
    ]);
    expect(calls.indexOf("roundRect(354,24,72,13,2)")).toBeLessThan(calls.indexOf("strokeText(Q1ABC −3 dB,357,31)"));
  });

  it("writes what was heard in the line under way when that line is drawn, on that line", () => {
    const { canvas, calls } = fakeCanvas(560, 380);
    const painter = new Waterfall(canvas);
    line(painter, 0, START);
    painter.push(row(8), START + 200, false);
    calls.length = 0;
    painter.label("Q1ABC 2 dB", START + 300);
    expect(calls).toEqual([]);
    painter.push(row(8), START + 400, false);
    expect(drawn(calls, "fillText")).toEqual(["fillText(Q1ABC 2 dB,357,31)"]);
    expect(calls.indexOf("putImageData(560x1,0,22)")).toBeLessThan(calls.indexOf("fillText(Q1ABC 2 dB,357,31)"));
    calls.length = 0;
    line(painter, 0, START + 600);
    painter.push(row(0), START + 800, false);
    expect(texts(calls)).toEqual([]); // (it moves down with the picture and is not written again)
  });

  it("draws everything again from the lines it kept when the canvas has another size, the labels and the times with them", () => {
    const { canvas, calls, strips, resize } = fakeCanvas(420, 240);
    const painter = new Waterfall(canvas);
    for (let i = 0; i < 200; i++) line(painter, 0, START + 14_000 + i * 200);
    painter.label("Q1ABC −3 dB", START + 30_000);
    resize(560, 380);
    calls.length = 0;
    strips.length = 0;
    painter.push(row(0), START + 54_000, false);
    expect([canvas.width, canvas.height]).toEqual([560, 380]);
    expect(strips).toHaveLength(200); // (every line kept: the taller box shows more of them than the old one did)
    expect(strips.every((strip) => strip.width === 560)).toBe(true);
    expect(texts(calls)).toEqual(["12:00:15", "12:00:30", "12:00:45", "Q1ABC −3 dB", "500", "1000", "1500", "2000", "2500"]);
    expect(drawn(calls, "drawImage")).toEqual([]);
    calls.length = 0;
    painter.draw();
    expect(drawn(calls, "putImageData")).toHaveLength(200);
  });

  it("shows the picture as it stands at a moment: each row as far down as it is old, the time since the newest row a gap at the top, the labels on their lines", () => {
    const { canvas, calls, strips } = fakeCanvas(560, 380);
    const painter = new Waterfall(canvas);
    const rows = Array.from({ length: 50 }, (_, i) => ({ bytes: row(i < 25 ? 8 : 16), at: START + i * 100, tx: i >= 45 }));
    painter.show(rows, [{ at: START + 1000, text: "Q1OLD" }], START + 45_000);
    const lines = strips.map((strip) => strip.data.slice(0, 4)); // (drawn from the oldest: the newest, at the top, last)
    expect(lines).toHaveLength(225); // (the 5 s of rows and the 40 s since: the moment's own line is not whole)
    expect(strips[0].y).toBe(22 + 224); // (the line of the first row, 45 s ago, is 224 lines down)
    expect(strips.at(-1)?.y).toBe(22);
    expect(lines.slice(0, 12)).toEqual(Array.from({ length: 12 }, () => colourOf(8)));
    expect(lines.slice(13, 22)).toEqual(Array.from({ length: 9 }, () => colourOf(16)));
    expect(lines.slice(22)).toEqual(Array.from({ length: 203 }, () => GROUND)); // (ours with nothing over 24 dB, then the 40 s without rows)
    expect(calls.filter((call) => /^fillRect\(0,\d+,3,1\)$/.test(call))).toEqual(
      [198, 199, 200, 201, 202].reverse().map((depth) => `fillRect(0,${22 + depth},3,1)`),
    ); // (the mark of ours on its three lines and the two held after them)
    expect(drawn(calls, "fillText")).toContainEqual(`fillText(Q1OLD,357,${22 + 219 + 9})`); // (the label on the line of its moment, 44 s ago)
    expect(texts(calls).slice(0, 3)).toEqual(["12:00:00", "12:00:15", "12:00:30"]);
    expect(texts(calls)).toContain("12:00:15");
  });

  it("keeps two minutes of lines, forgets them all when it is cleared, and does nothing on a canvas that has no context", () => {
    const { canvas, strips } = fakeCanvas(300, 900);
    const painter = new Waterfall(canvas);
    for (let i = 0; i < KEPT_LINES + 50; i++) line(painter, 0, START + i * 200);
    strips.length = 0;
    painter.draw();
    expect(strips).toHaveLength(KEPT_LINES);
    strips.length = 0;
    painter.clear();
    expect(strips).toEqual([]);
    painter.label("Q1ABC 3 dB", START);
    const hidden = fakeCanvas(0, 0); // (in a fold that is closed: nothing is drawn, and the lines are kept)
    const unseen = new Waterfall(hidden.canvas);
    line(unseen, 0, START);
    unseen.push(row(0), START + 200, false);
    expect(hidden.calls).toEqual([]);
    hidden.resize(420, 240);
    unseen.draw();
    expect(hidden.strips).toHaveLength(1);
    const dead = document.createElement("canvas");
    vi.spyOn(dead, "getContext").mockReturnValue(null);
    const none = new Waterfall(dead);
    expect(() => {
      line(none, 0, START);
      none.label("Q1ABC 3 dB", START);
      none.draw();
      none.show([], [], START);
      none.clear();
    }).not.toThrow();
  });
});

describe("the painter at the monitor card's speeds", () => {
  const START = new Date(2026, 10, 13, 12, 0, 0).getTime();
  const row = (db: number): Uint8Array => new Uint8Array(BINS).fill(byteOfDb(db));
  const drawn = (calls: string[], name: string): string[] => calls.filter((call) => call.startsWith(`${name}(`));
  const texts = (calls: string[]): string[] => drawn(calls, "fillText").map((call) => call.slice("fillText(".length).split(",")[0]);
  const colourOf = (db: number): number[] => Array.from(colourTable(SCALE).subarray(byteOfDb(db) * 4, byteOfDb(db) * 4 + 4));
  /** The rows of a stretch, one every `step` ms from `from` (oldest first), all at `db`. */
  const rows = (from: number, until: number, step: number, db = 0) =>
    Array.from({ length: Math.ceil((until - from) / step) }, (_, i) => ({ bytes: row(db), at: from + i * step, tx: false }));
  /** Where a strip of the picture ends: its own height, or the height it was cut to. */
  const bottoms = (calls: string[]): number[] =>
    drawn(calls, "putImageData").map((call) => {
      const [size, , y, , , , cut] = call.slice("putImageData(".length, -1).split(",");
      return Number(y) + (cut === undefined ? Number(size.split("x")[1]) : Number(cut));
    });

  afterEach(() => {
    document.body.replaceChildren();
    vi.unstubAllGlobals();
  });

  it("is today's picture, call for call and pixel for pixel, when no speed is given and at Normal", () => {
    const [a, b] = [fakeCanvas(560, 380), fakeCanvas(560, 380)];
    const [plain, normal] = [new Waterfall(a.canvas), new Waterfall(b.canvas, "normal")];
    for (const painter of [plain, normal]) {
      painter.show(rows(START, START + 20_000, 118), [{ at: START + 5_000, text: "Q1OLD" }], START + 20_000);
      for (let i = 0; i < 200; i++) painter.push(row(i % 40 < 10 ? 20 : 0), START + 20_000 + i * 118, i % 60 > 50);
      painter.label("Q1NEW 3 dB", START + 30_000);
    }
    expect(b.calls).toEqual(a.calls);
    expect(b.strips).toEqual(a.strips);
  });

  it("at Fast moves the picture down two lines of the screen for each line, cuts the last at the picture's bottom, and leaves the ruler, the curve and the time's thin line where and as they are", () => {
    const { canvas, calls } = fakeCanvas(420, 240);
    const l = layout(420, 240);
    const painter = new Waterfall(canvas, "fast");
    painter.show(rows(START, START + 60_000, 118), [], START + 60_000);
    expect([canvas.width, canvas.height]).toEqual([420, 240]);
    expect(drawn(calls, "putImageData")).toHaveLength(Math.ceil(l.rows / 2)); // (85 lines of two pixels for 169 pixels)
    expect(drawn(calls, "putImageData").at(-1)).toBe("putImageData(420x2,0,22)"); // (the newest at the top, two pixels high)
    expect(calls).toContain(`putImageData(420x2,0,${l.picture.y + l.picture.h - 1},0,0,420,1)`); // (the oldest one seen, cut to the one pixel left)
    expect(Math.max(...bottoms(calls))).toBe(l.picture.y + l.picture.h);
    expect(calls).toContain(`fillRect(0,0,420,${l.ruler.h})`);
    expect(calls).toContain(`fillRect(0,${l.curve.y - 1},420,${l.curve.h + 1})`); // (the curve's box where it is at Normal)
    expect(calls[calls.indexOf(`fillRect(0,${l.picture.y + 2 * 74},420,1)`) - 1]).toBe("fillStyle=grid"); // (the quarter 15 s ago, 74 lines under the newest: its line one CSS pixel thin)
    expect(calls).toContain(`fillText(12:00:45,8,${l.picture.y + 2 * 74 + 2 + 9})`); // (its time under the line of two pixels)
    calls.length = 0;
    for (let i = 0; i <= 2; i++) painter.push(row(0), START + 60_000 + i * 118, false);
    expect(drawn(calls, "drawImage")).toEqual([`drawImage(itself,0,22,420,${l.picture.h - 2},0,24,420,${l.picture.h - 2})`]);
    expect(drawn(calls, "putImageData")).toEqual(["putImageData(420x2,0,22)"]);
  });

  it("at Fast places a label by lines of two pixels, so no label is written over another", () => {
    const { canvas, calls } = fakeCanvas(560, 380);
    const painter = new Waterfall(canvas, "fast");
    painter.show(rows(START, START + 20_000, 118), [], START + 20_000);
    calls.length = 0;
    painter.label("Q1AAA", START + 19_000);
    painter.label("Q1BBB", START + 19_000);
    painter.label("Q1CCC", START + 19_000);
    painter.label("Q1DDD", START + 19_000); // (right, left and at the right edge are taken: nine lines of two pixels down)
    const ys = drawn(calls, "fillText").map((call) => Number(call.slice(0, -1).split(",").at(-1)));
    const top = 22 + 2 * (Math.floor((START + 20_000) / 200) - 1 - Math.floor((START + 19_000) / 200)) + 9;
    expect(ys).toEqual([top, top, top, top + 2 * 9]);
  });

  it("at Slow makes a line of each two fifths of a second, its four rows averaged in power, writes the time on the line that holds the quarter, and draws the curve's bright line of its newest three lines", () => {
    const { canvas, calls, strips } = fakeCanvas(560, 380);
    const painter = new Waterfall(canvas, "slow");
    [0, 10, 0, 10].forEach((db, i) => painter.push(row(db), START + i * 100, false));
    expect(strips).toEqual([]);
    painter.push(row(0), START + 400, false);
    const mean = lineOf([row(0), row(10), row(0), row(10)], false)[0];
    expect(strips.map((strip) => strip.data.slice(0, 4))).toEqual([Array.from(colourTable(SCALE).subarray(mean * 4, mean * 4 + 4))]);
    painter.clear();
    calls.length = 0;
    const written: [number, string[]][] = [];
    for (let i = 0; i <= 310; i++) {
      const before = calls.length;
      painter.push(row(0), START + i * 100, false);
      const said = texts(calls.slice(before));
      if (said.length > 0) written.push([i, said]);
    }
    expect(written).toEqual([
      [4, ["12:00:00"]], // (the first line, from 0 to 0.4 s, whole when the row at 0.4 s comes)
      [152, ["12:00:15"]], // (15 s falls in the line from 14.8 to 15.2 s: its own time, not 12:00:14)
      [304, ["12:00:30"]],
    ]);
    painter.clear();
    const curve = layout(560, 380).curve;
    for (const [i, db] of [40, 40, 12, 12, 12].entries()) for (const ms of [0, 100, 200, 300]) painter.push(row(db), START + i * 400 + ms, false);
    calls.length = 0;
    painter.push(row(12), START + 2000, false);
    const [, y] = drawn(calls, "lineTo").at(-2)?.slice("lineTo(".length, -1).split(",").map(Number) ?? [];
    expect(y).toBe(curve.y + Math.round(0.5 * (curve.h - 1)) + 0.5); // (12 dB: the mean of the newest 1.2 s, without the 40 dB before it)
  });

  it.each(["slow", "normal", "fast"] as const)("at %s has the two minutes the page keeps whole, with no gap where there were rows", (speed: Speed) => {
    const { canvas, strips } = fakeCanvas(300, 1600); // (a picture taller than any: every line kept is seen)
    const painter = new Waterfall(canvas, speed);
    const now = START + 120_000;
    painter.show(rows(START, now, 118), [], now);
    expect(strips).toHaveLength(keptLines(PACE[speed].lineMs));
    expect(strips.every((strip) => strip.data.slice(0, 4).join() === colourOf(0).join())).toBe(true);
  });

  it("at Slow on a screen of 1.25 pixels to the CSS pixel leaves the ground under the two minutes, and moves nothing older into it", () => {
    vi.stubGlobal("devicePixelRatio", 1.25);
    const { canvas, calls, strips } = fakeCanvas(560, 380);
    const l = layout(560, 380, 1.25);
    expect([l.rowPx, l.rows]).toEqual([1, 351]);
    const painter = new Waterfall(canvas, "slow");
    const now = START + 120_000;
    painter.show(rows(START, now, 118), [{ at: START + 500, text: "Q1OLD" }], now);
    expect(strips).toHaveLength(300);
    expect(Math.max(...strips.map((strip) => strip.y))).toBe(l.picture.y + 299);
    expect(texts(calls)).toContain("12:00:00"); // (the time and the label on the oldest lines kept are written, and end where the lines kept end: they would be wiped from the ground under them as the picture moves)
    expect(texts(calls)).toContain("Q1OLD");
    expect(drawn(calls, "rect").length).toBeGreaterThanOrEqual(2);
    for (const clip of drawn(calls, "rect")) expect(clip).toBe(`rect(0,${l.picture.y},${l.width},300)`);
    calls.length = 0;
    for (let i = 0; i < 50; i++) painter.push(row(0), now + i * 118, false);
    const copies = calls.flatMap((call, i) => (call.startsWith("drawImage(") ? [i] : []));
    expect(copies.length).toBeGreaterThan(10);
    for (const at of copies) expect(calls.slice(at + 1, at + 3)).toEqual(["fillStyle=#000828", `fillRect(0,${l.picture.y + 300},${l.width},51)`]);
    expect(Math.max(...bottoms(calls))).toBeLessThanOrEqual(l.picture.y + 300);
  });

  it("draws the picture again in place at another speed: the canvas keeps its size and a label stands on the line of its moment", () => {
    const { canvas, calls } = fakeCanvas(560, 380);
    const painter = new Waterfall(canvas);
    const now = START + 45_000;
    const shown = (): void => painter.show(rows(START, now, 118), [{ at: START + 40_000, text: "Q1OLD" }], now);
    shown();
    expect(calls).toContain("fillText(Q1OLD,357,55)"); // (24 lines of a fifth of a second down)
    for (const [speed, y] of [
      ["slow", 22 + 11 + 9],
      ["fast", 22 + 2 * 24 + 9],
      ["normal", 55],
    ] as const) {
      calls.length = 0;
      painter.setSpeed(speed);
      shown();
      expect([canvas.width, canvas.height]).toEqual([560, 380]);
      expect(calls).toContain(`fillText(Q1OLD,357,${y})`);
      expect(painter.slot(START + 1000)).toBe(Math.floor((START + 1000) / PACE[speed].lineMs));
    }
  });
});
