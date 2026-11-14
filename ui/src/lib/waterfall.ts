// The HF radio's waterfall drawn as a rig draws it, the numbers it is drawn by: the passband at the modem's own bins, a row for every two of its spectra and a line of the picture for every two rows; the colour of a bin
// over the floor (lib/waterfallfloor.ts finds the floor); where the ruler, the picture and the curve stand in a box of any size; the ticks of the ruler; the time and the SNR as they are written; where the call of what was
// heard is written; and the curve. The painter that keeps a canvas up to date with them is lib/waterfallpainter.ts.
// The passband, the band of a frame and the modem's spectrum are the daemon's, through LIMITS (neoaprs/mercuryscope.py).
import { LIMITS } from "@/protocol/lists";

const { loHz, hiHz, signalLoHz, signalHiHz, modemRate, modemBins, rowFirstBin, rowBins, rowSpectra, historySec } = LIMITS.scope;
/** The modem makes a spectrum every 50 ms by its timer (what comes is nearer seventeen a second: these rates say how long a line is and how slowly the floor learns; a row is of the moment it was made). */
const MODEM_SPECTRA_PER_SECOND = 20;

/** The width of a bin of the modem: 7.8 Hz. */
export const BIN_HZ = modemRate / 2 / modemBins;
/** The modem's bin that is the first of the passband, the first of a row the daemon sends. */
const FIRST_BIN = rowFirstBin;
/** The modem's bins that lie in the passband: 307 of them, the bins of a row. */
export const BINS = rowBins;
/** A row is this many of the modem's spectra averaged in power, so there are up to ten rows a second: what the floor learns from and what the painter is given. */
export const SPECTRA_PER_ROW = rowSpectra;
export const ROWS_PER_SECOND = MODEM_SPECTRA_PER_SECOND / SPECTRA_PER_ROW;
/** A line of the picture is the time of this many rows by the modem's timer, the rows made in it averaged in power: five lines a second (lib/waterfalllines.ts puts a row in the line of its moment). A frame of 3.8 s is nineteen
 * lines high, higher than the label beside it, the box in Settings holds forty seconds and the card over the map more than a minute, and the noise of a line is about half as rough as that of a row, so a weak frame stands out of
 * it sooner. With lines of three rows, frames five seconds apart would stand closer than their labels are high. */
export const ROWS_PER_LINE = 2;
export const LINES_PER_SECOND = ROWS_PER_SECOND / ROWS_PER_LINE;
/** Two minutes of lines are kept, as long as the daemon keeps its rows (LIMITS.scope.historySec), more than the tallest picture holds (the monitor card's 380 pixels at a ratio of 1.5 make four hundred lines, eighty seconds), so
 * that a box whose size or pixel ratio changes is filled again whole. */
export const KEPT_LINES = historySec * LINES_PER_SECOND;

/** Where a frequency above the dial is among the bins of the passband, with its fraction: bin 0 is centred on the first bin's frequency. */
export const binOfHz = (hz: number): number => hz / BIN_HZ - FIRST_BIN;
/** The frequency a bin of the passband is centred on. */
export const hzOfBin = (bin: number): number => (FIRST_BIN + bin) * BIN_HZ;

// A bin of a row is one byte: a quarter of a dB to the step, from 16 dB under the floor (deeper than the noise dips) to 48 dB over it.
const BYTE_MIN_DB = -16;
const BYTE_STEP_DB = 0.25;
export const dbOfByte = (byte: number): number => BYTE_MIN_DB + byte * BYTE_STEP_DB;
export const byteOfDb = (db: number): number => Math.max(0, Math.min(255, Math.round((db - BYTE_MIN_DB) / BYTE_STEP_DB)));
/** The power each byte stands for, worked once: a line is made of a few rows' powers. */
const POWER_OF_BYTE = Float64Array.from({ length: 256 }, (_, byte) => 10 ** (dbOfByte(byte) / 10));

/** A colour as its red, green and blue, 0 to 255. */
export type Rgb = readonly [number, number, number];

/** The dB over the floor at which each of the five colours of the scale stands, set for what is heard: the ground well under the floor; the blue where a frame the modem can just read stands (its bins 7 to 9 dB over the floor);
 * the cyan where a frame of a good signal does (14 dB at an SNR of 6); its strongest bins and a strong station go through green to yellow, and the red is a signal 33 dB and more over the noise. */
const COLOUR_DB = [-10, 8, 14, 23, 33] as const;
/** Between the ground and the blue the colour grows as the cube of the dB: the noise of a line, which is spread from 6 dB under the floor to 4 over it, is a fine grain in the dark third of that stretch, and what stands 6 dB over
 * the floor is already lighter than all but a speck of it. */
const WEAK_END = 3;

/** Our own transmission is drawn this much lower than it is. As played it stands 35 to 47 dB over the floor, more than any station heard: drawn so, it would be the brightest thing in the picture, with streaks beside it from
 * edge to edge, and the scale would have to end where it does and not where stations are. Lower by this much its carriers are stripes of cyan to yellow like a good station's and the streaks are gone into the ground; the strip
 * along the left edge and the ruler's bracket say that the lines are ours. */
const OWN_DOWN_DB = 24;

/** The mean of rows in power, bin by bin, on the scale of the bytes (not rounded); the lowest a byte tells where there is no row. */
function powerMean(rows: readonly ArrayLike<number>[]): Float32Array {
  const out = new Float32Array(BINS);
  const count = Math.max(1, rows.length);
  for (let i = 0; i < BINS; i++) {
    let power = 0;
    for (const row of rows) power += POWER_OF_BYTE[row[i]];
    out[i] = Math.max(0, (10 * Math.log10(power / count + 1e-30) - BYTE_MIN_DB) / BYTE_STEP_DB);
  }
  return out;
}

/** A line of the picture from the rows that fall into it (Floor.over made them): each bin the mean of its powers, and a line of our own transmission OWN_DOWN_DB lower. */
export function lineOf(rows: readonly Uint8Array[], own: boolean): Uint8Array {
  return Uint8Array.from(powerMean(rows), (byte) => byteOfDb(dbOfByte(byte) - (own ? OWN_DOWN_DB : 0)));
}

/** Whether a row of our own transmission has nothing of ours in it: the radio is keyed and the audio has not begun, or it has ended and the modem's buffer is empty. No bin of it would stand over the floor as it is drawn. */
export const silentOwn = (row: Uint8Array): boolean => !row.some((byte) => byte > byteOfDb(OWN_DOWN_DB));

/** Where a bin so many dB over the floor is on the scale of the five colours: 0 at the first and 4 at the last, never lower for a stronger bin. */
export function scalePosition(db: number): number {
  const last = COLOUR_DB.length - 1;
  if (db <= COLOUR_DB[0]) return 0;
  for (let i = 0; i < last; i++) {
    if (db >= COLOUR_DB[i + 1]) continue;
    const part = (db - COLOUR_DB[i]) / (COLOUR_DB[i + 1] - COLOUR_DB[i]);
    return i + (i === 0 ? part ** WEAK_END : part);
  }
  return last;
}

function toHsv([r, g, b]: Rgb): [number, number, number] {
  const [high, low] = [Math.max(r, g, b), Math.min(r, g, b)];
  const spread = high - low;
  const hue = spread === 0 ? 0 : high === r ? ((g - b) / spread + 6) % 6 : high === g ? (b - r) / spread + 2 : (r - g) / spread + 4;
  return [hue * 60, high === 0 ? 0 : spread / high, high / 255];
}

function fromHsv(hue: number, saturation: number, value: number): Rgb {
  const channel = (n: number): number => {
    const k = (n + hue / 60) % 6;
    return 255 * (value - value * saturation * Math.max(0, Math.min(k, 4 - k, 1)));
  };
  return [channel(5), channel(3), channel(1)];
}

/** The colour a part of the way from one colour of the scale to the next: the hue turns the short way round the colour circle while the saturation and the brightness go straight, so that cyan becomes yellow through green, as on a rig,
 * and not through grey. */
function mix(from: Rgb, to: Rgb, part: number): Rgb {
  const [a, b] = [toHsv(from), toHsv(to)];
  const turn = ((b[0] - a[0] + 540) % 360) - 180;
  return fromHsv((a[0] + turn * part + 360) % 360, a[1] + (b[1] - a[1]) * part, a[2] + (b[2] - a[2]) * part);
}

/** The colour of every byte: 256 pixels of red, green, blue and alpha, from the five colours of the scale. */
export function colourTable(scale: readonly Rgb[]): Uint8ClampedArray {
  const table = new Uint8ClampedArray(256 * 4).fill(255);
  if (scale.length < 2) return table;
  for (let byte = 0; byte < 256; byte++) {
    const at = (scalePosition(dbOfByte(byte)) / (COLOUR_DB.length - 1)) * (scale.length - 1);
    const i = Math.min(scale.length - 2, Math.floor(at));
    table.set(mix(scale[i], scale[i + 1], at - i), byte * 4);
  }
  return table;
}

/** The values of a line across `width` pixels of the passband. Where a bin is two pixels wide and more (a screen of two or three pixels to the CSS pixel) every pixel is its nearest bin: a bin is a crisp cell, as a line is,
 * and not a smear from one bin to the next. Where a bin is narrower than that, a pixel is part of the way from one bin to the other; and where a pixel covers several bins it is the strongest of them, so that a carrier one bin
 * wide is not lost in a narrow box. */
export function spread(values: ArrayLike<number>, width: number): Float32Array {
  const out = new Float32Array(width);
  const each = (hiHz - loHz) / BIN_HZ / width; // bins to a pixel
  for (let x = 0; x < width; x++) {
    const at = binOfHz(loHz + ((x + 0.5) / width) * (hiHz - loHz));
    if (each <= 0.5) out[x] = values[Math.max(0, Math.min(BINS - 1, Math.round(at)))];
    else if (each <= 1) {
      const lo = Math.max(0, Math.min(BINS - 1, Math.floor(at)));
      const hi = Math.min(BINS - 1, lo + 1);
      out[x] = values[lo] + (values[hi] - values[lo]) * Math.max(0, Math.min(1, at - lo));
    } else {
      let top = -Infinity;
      for (let bin = Math.max(0, Math.round(at - each / 2)); bin <= Math.min(BINS - 1, Math.round(at + each / 2)); bin++) top = Math.max(top, values[bin]);
      out[x] = top;
    }
  }
  return out;
}

/** A rectangle of the canvas, in its own (device) pixels. */
export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Where everything stands in a box: the ruler along the top, the picture under it (a whole number of rows), a rule, and the curve at the bottom; and the sizes of the small things, all in the canvas's own pixels. */
export interface Layout {
  width: number;
  height: number;
  ruler: Box;
  picture: Box;
  curve: Box;
  /** How many pixels a line of the picture is high (one CSS pixel, a whole number of the screen's) and how many lines are seen. */
  rowPx: number;
  rows: number;
  /** One CSS pixel, the height of small text (the page's smallest: 11 pixels) and of the room a label takes, and the strip along the left edge where the times and the mark of a transmission stand and no label goes. */
  unit: number;
  text: number;
  plate: number;
  gutter: number;
}

/** The layout of a box so many CSS pixels wide and high on a screen of that pixel ratio: the same for the box in Settings, the card over the map and a phone. */
export function layout(cssWidth: number, cssHeight: number, ratio = 1): Layout {
  const px = (css: number): number => Math.max(1, Math.round(css * ratio));
  const [width, height] = [px(cssWidth), px(cssHeight)];
  const rowPx = Math.max(1, Math.round(ratio));
  const ruler = Math.min(px(22), Math.max(1, Math.floor(height / 5)));
  const curve = Math.min(px(Math.max(40, Math.min(80, cssHeight * 0.2))), Math.max(1, Math.floor(height / 3))); // a fifth of the box: the waterfall is the main thing
  const rule = px(1);
  const rows = Math.max(1, Math.floor((height - ruler - curve - rule) / rowPx));
  const below = ruler + rows * rowPx + rule;
  return {
    width,
    height,
    ruler: { x: 0, y: 0, w: width, h: ruler },
    picture: { x: 0, y: ruler, w: width, h: rows * rowPx },
    curve: { x: 0, y: below, w: width, h: Math.max(1, height - below) },
    rowPx,
    rows,
    unit: px(1),
    text: px(11),
    plate: px(16),
    gutter: px(64),
  };
}

/** Where a frequency is across `width` pixels of the passband. */
export const xOfHz = (hz: number, width: number): number => Math.round(((hz - loHz) / (hiHz - loHz)) * width);

/** A tick of the ruler: its frequency, where it is, and whether it is a long one with its number. */
export interface Tick {
  hz: number;
  x: number;
  numbered: boolean;
}

/** The ticks of a ruler `width` pixels wide: one every 100 Hz, and a number every 500, or every 1000 where the numbers, each needing `room` pixels, would touch. */
export function rulerTicks(width: number, room: number): Tick[] {
  const every = xOfHz(loHz + 500, width) >= room ? 500 : 1000;
  const ticks: Tick[] = [];
  for (let hz = Math.ceil(loHz / 100) * 100; hz <= hiHz; hz += 100) ticks.push({ hz, x: Math.min(width - 1, xOfHz(hz, width)), numbered: hz % every === 0 });
  return ticks;
}

/** The time of a line as the waterfall writes it: hh:mm:ss in the viewer's time, as the page writes the time of a packet (clockText of lib/format.ts), so that a frame's line and its packet say the same. */
export function timeText(at: number): string {
  const time = new Date(at);
  return [time.getHours(), time.getMinutes(), time.getSeconds()].map((n) => String(n).padStart(2, "0")).join(":");
}

/** The SNR of what was heard as the waterfall writes it beside the call: whole dB, a minus that is a minus sign ("−3"). */
export function snrText(db: number): string {
  const whole = Math.round(db);
  return `${whole < 0 ? "\u2212" : ""}${Math.abs(whole)}`;
}

const TIME_EVERY_MS = 15_000;
/** Whether a line at `at` (milliseconds) is the first of a quarter of a minute, the line before it having been at `before`: the time is written on it. */
export const startsQuarter = (before: number, at: number): boolean => Math.floor(at / TIME_EVERY_MS) > Math.floor(before / TIME_EVERY_MS);

/** Where a label stands: on the line of that number (lines are counted as they come), from there down over the older ones, and from `x` across `w` pixels. */
export interface Slot {
  row: number;
  x: number;
  w: number;
}

/** Where the label of what was heard goes, `w` pixels wide, for a frame that ended on line `row`: beside the band of a frame, right of it, else left of it, else against the right edge; and where another label stands there already, one
 * and two labels' heights further down. Null when every such place is taken: a label is never written over another, nor over the times at the left edge. */
export function placeLabel(row: number, w: number, taken: readonly Slot[], l: Layout): Slot | null {
  const gap = 4 * l.unit;
  const high = Math.ceil((l.plate + l.unit) / l.rowPx); // lines a label covers, with a pixel of air
  const [right, left] = [xOfHz(signalHiHz, l.width) + gap, xOfHz(signalLoHz, l.width) - gap - w];
  const places = [right + w <= l.width - gap ? [right] : [], left >= l.gutter ? [left] : [], [Math.max(l.gutter, l.width - gap - w)]].flat();
  for (let down = 0; down < 3; down++) {
    for (const x of places) {
      const slot = { row: row - down * high, x, w };
      if (!taken.some((other) => Math.abs(other.row - slot.row) < high && other.x < x + w && x < other.x + other.w)) return slot;
    }
  }
  return null;
}

/** The points of the curve's line for the heights `ys` of the bins (each in pixels, the bin's own): one at the centre of every bin across `width` pixels of the passband, and the first and the last carried to the edges, so that a line
 * drawn straight from point to point runs the whole width and does not step. */
export function curvePoints(ys: ArrayLike<number>, width: number): { x: number; y: number }[] {
  const points = Array.from({ length: ys.length }, (_, i) => ({ x: ((hzOfBin(i) - loHz) / (hiHz - loHz)) * width, y: ys[i] }));
  return ys.length === 0 ? [] : [{ x: 0, y: ys[0] }, ...points, { x: width, y: ys[ys.length - 1] }];
}

/** The plate behind a label that stands in `slot`, its text written around the line `middle`: the slot's width (it already holds the three pixels of air at each side), a pixel above and under the text's height. */
export function plateRect(slot: Slot, middle: number, l: Layout): Box {
  const h = l.text + 2 * l.unit;
  return { x: slot.x, y: middle - Math.round(h / 2), w: slot.w, h };
}

const CURVE_MEAN_LINES = 2 * LINES_PER_SECOND; // the quiet shape is the mean of the last two seconds, in dB
const CURVE_NOW_LINES = LINES_PER_SECOND; // the bright line is the mean of the last second, in power: a calm line, as a rig's, where one line alone jumps 5 dB from bin to bin and half a second of them still 3

/** The newest of `lines` (the newest first), up to `count` of them, and none from before we last began or stopped sending. */
function newest<T extends { tx: boolean }>(lines: readonly T[], count: number): T[] {
  const other = lines.findIndex((line) => line.tx !== lines[0].tx);
  return lines.slice(0, Math.min(count, other < 0 ? lines.length : other));
}

/** The quiet shape under the curve: the mean, in dB, of the newest lines (`lines`, the newest first) of the last two seconds, and of none from before we last began or stopped sending: in a mean with our own signal,
 * a signal that is not there would stand for two seconds after every transmission of ours. */
export function curveMean(lines: readonly { bytes: Uint8Array; tx: boolean }[]): Float32Array {
  const last = newest(lines, CURVE_MEAN_LINES);
  return Float32Array.from({ length: BINS }, (_, i) => last.reduce((sum, line) => sum + line.bytes[i], 0) / Math.max(1, last.length));
}

/** The bright line of the curve: the mean, in power, of the lines of the last second, with the same care about our own transmission. Over the noise it lies on the floor's line, which is the noise's mean power. */
export function curveNow(lines: readonly { bytes: Uint8Array; tx: boolean }[]): Float32Array {
  return powerMean(newest(lines, CURVE_NOW_LINES).map((line) => line.bytes));
}
