// Numbers the HF radio's waterfall is drawn by: passband bins, rows and lines, the colour scale,
// layout, ruler ticks, label text and placement, and the curve. The floor is in waterfallfloor.ts
// and the canvas painter in waterfallpainter.ts. Passband and spectrum rates come from the daemon
// via LIMITS.
import { LIMITS } from "@/protocol/lists";

const { loHz, hiHz, signalLoHz, signalHiHz, modemRate, modemBins, rowFirstBin, rowBins, rowSpectra, historySec } = LIMITS.scope;
/** The modem's spectrum interval; the real rate is nearer 17 a second. */
const MODEM_SPECTRA_PER_SECOND = 20;

/** Width of a modem bin: 7.8 Hz. */
export const BIN_HZ = modemRate / 2 / modemBins;
/** First modem bin of the passband, and of each row the daemon sends. */
const FIRST_BIN = rowFirstBin;
/** Number of modem bins in the passband (307), the bins of a row. */
export const BINS = rowBins;
/** A row averages this many spectra in power: up to ten rows a second. */
export const SPECTRA_PER_ROW = rowSpectra;
export const ROWS_PER_SECOND = MODEM_SPECTRA_PER_SECOND / SPECTRA_PER_ROW;
/**
 * A line of the picture is this many rows averaged in power: five lines a second at Normal speed.
 * Lines of three rows would put frames five seconds apart closer than their labels are high.
 */
export const ROWS_PER_LINE = 2;
export const LINES_PER_SECOND = ROWS_PER_SECOND / ROWS_PER_LINE;
/** Lines that fit the two minutes the daemon keeps rows for (LIMITS.scope.historySec). */
export const keptLines = (lineMs: number): number => (historySec * 1000) / lineMs;
/** Two minutes of lines are kept, so a resized box can be redrawn whole. */
export const KEPT_LINES = keptLines(1000 / LINES_PER_SECOND);

/** Speeds of the monitor card's waterfall; the box in Settings is always Normal. */
export type Speed = "slow" | "normal" | "fast";
export const SPEEDS: readonly Speed[] = ["slow", "normal", "fast"];
/**
 * A speed: how long a line is (its rows averaged in power) and how many screen lines high it is
 * drawn. Slow uses lines of twice the time; Fast draws Normal lines twice as high.
 */
export const PACE: Record<Speed, { lineMs: number; tall: number }> = {
  slow: { lineMs: 2000 / LINES_PER_SECOND, tall: 1 },
  normal: { lineMs: 1000 / LINES_PER_SECOND, tall: 1 },
  fast: { lineMs: 1000 / LINES_PER_SECOND, tall: 2 },
};

/** Fractional bin position of a frequency above the dial; bin 0 is centred on the first bin. */
export const binOfHz = (hz: number): number => hz / BIN_HZ - FIRST_BIN;
export const hzOfBin = (bin: number): number => (FIRST_BIN + bin) * BIN_HZ;

// A row byte is a quarter of a dB, from 16 dB under the floor to 48 dB over it.
const BYTE_MIN_DB = -16;
const BYTE_STEP_DB = 0.25;
export const dbOfByte = (byte: number): number => BYTE_MIN_DB + byte * BYTE_STEP_DB;
export const byteOfDb = (db: number): number => Math.max(0, Math.min(255, Math.round((db - BYTE_MIN_DB) / BYTE_STEP_DB)));
/** The power each byte value stands for. */
const POWER_OF_BYTE = Float64Array.from({ length: 256 }, (_, byte) => 10 ** (dbOfByte(byte) / 10));

export type Rgb = readonly [number, number, number];

/**
 * dB over the floor of each of the five scale colours: ground, blue (a frame the modem can just
 * read), cyan (a good signal), green to yellow (strong), red (33 dB and more over the noise).
 */
const COLOUR_DB = [-10, 8, 14, 23, 33] as const;
/**
 * Between ground and blue the colour grows as the cube of the dB, so the fine noise grain stays
 * dark.
 */
const WEAK_END = 3;

/** Our own transmission is drawn this much lower, so it does not outshine every station heard. */
const OWN_DOWN_DB = 24;

/** Mean power of the rows per bin, on the byte scale (unrounded); no rows gives the lowest byte. */
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

/** One line of the picture from the rows in it; our own transmission is OWN_DOWN_DB lower. */
export function lineOf(rows: readonly Uint8Array[], own: boolean): Uint8Array {
  return Uint8Array.from(powerMean(rows), (byte) => byteOfDb(dbOfByte(byte) - (own ? OWN_DOWN_DB : 0)));
}

/**
 * True when a row of our own transmission holds none of it: keyed before the audio, or after it
 * ended.
 */
export const silentOwn = (row: Uint8Array): boolean => !row.some((byte) => byte > byteOfDb(OWN_DOWN_DB));

/**
 * Position of a bin `db` over the floor on the five-colour scale, 0 to 4; never lower for a
 * stronger bin.
 */
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

/**
 * The colour part of the way between two scale colours. The hue turns the short way round, so cyan
 * becomes yellow through green and not through grey.
 */
function mix(from: Rgb, to: Rgb, part: number): Rgb {
  const [a, b] = [toHsv(from), toHsv(to)];
  const turn = ((b[0] - a[0] + 540) % 360) - 180;
  return fromHsv((a[0] + turn * part + 360) % 360, a[1] + (b[1] - a[1]) * part, a[2] + (b[2] - a[2]) * part);
}

/** Red, green, blue and alpha of every byte value (256 pixels). */
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

/**
 * The values of a line across `width` pixels of the passband. Bins two or more pixels wide use the
 * nearest bin, so they stay crisp cells; narrower bins are interpolated; where a pixel covers
 * several bins it takes the strongest, so a one-bin carrier is not lost.
 */
export function spread(values: ArrayLike<number>, width: number): Float32Array {
  const out = new Float32Array(width);
  const each = (hiHz - loHz) / BIN_HZ / width;
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

/** A rectangle of the canvas in device pixels. */
export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

/**
 * Layout of a box in canvas pixels: ruler on top, the picture (whole rows), a rule, the curve
 * below.
 */
export interface Layout {
  width: number;
  height: number;
  ruler: Box;
  picture: Box;
  curve: Box;
  /** Pixel height of a line (a whole number of screen pixels) and the number of lines shown. */
  rowPx: number;
  rows: number;
  /** Small sizes: a CSS pixel, text height, label room, and the left strip kept free of labels. */
  unit: number;
  text: number;
  plate: number;
  gutter: number;
}

/**
 * Layout for a box of given CSS size and pixel ratio; the same for Settings, the card and a phone.
 */
export function layout(cssWidth: number, cssHeight: number, ratio = 1): Layout {
  const px = (css: number): number => Math.max(1, Math.round(css * ratio));
  const [width, height] = [px(cssWidth), px(cssHeight)];
  const rowPx = Math.max(1, Math.round(ratio));
  const ruler = Math.min(px(22), Math.max(1, Math.floor(height / 5)));
  // The curve takes a fifth of the box; the waterfall is the main part.
  const curve = Math.min(px(Math.max(40, Math.min(80, cssHeight * 0.2))), Math.max(1, Math.floor(height / 3)));
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

export const xOfHz = (hz: number, width: number): number => Math.round(((hz - loHz) / (hiHz - loHz)) * width);

/** A ruler tick: its frequency, position, and whether it is long (with a number). */
export interface Tick {
  hz: number;
  x: number;
  numbered: boolean;
}

/**
 * Ticks for a ruler `width` pixels wide: one per 100 Hz, a number every 500 Hz (1000 Hz if they
 * would touch).
 */
export function rulerTicks(width: number, room: number): Tick[] {
  const every = xOfHz(loHz + 500, width) >= room ? 500 : 1000;
  const ticks: Tick[] = [];
  for (let hz = Math.ceil(loHz / 100) * 100; hz <= hiHz; hz += 100) ticks.push({ hz, x: Math.min(width - 1, xOfHz(hz, width)), numbered: hz % every === 0 });
  return ticks;
}

/** hh:mm:ss in the viewer's time, as clockText of lib/format.ts writes a packet's time. */
export function timeText(at: number): string {
  const time = new Date(at);
  return [time.getHours(), time.getMinutes(), time.getSeconds()].map((n) => String(n).padStart(2, "0")).join(":");
}

/** SNR as written beside a call: whole dB with a real minus sign ("−3"). */
export function snrText(db: number): string {
  const whole = Math.round(db);
  return `${whole < 0 ? "\u2212" : ""}${Math.abs(whole)}`;
}

const TIME_EVERY_MS = 15_000;
/** The quarter-minute in the line starting at `at` and `lineMs` long, or null if none. */
export function quarterIn(at: number, lineMs: number): number | null {
  const quarter = Math.ceil(at / TIME_EVERY_MS) * TIME_EVERY_MS;
  return quarter < at + lineMs ? quarter : null;
}

/**
 * Where a label stands: from the line of that number down over older lines, from `x` across `w`
 * pixels.
 */
export interface Slot {
  row: number;
  x: number;
  w: number;
}

/**
 * Where the label of a heard frame (`w` pixels wide, ending on line `row`) goes: beside the band,
 * else right of it, else left, else against the right edge; further down when taken. Null when
 * every place is taken, so a label never covers another or the times.
 */
export function placeLabel(row: number, w: number, taken: readonly Slot[], l: Layout): Slot | null {
  const gap = 4 * l.unit;
  const high = Math.ceil((l.plate + l.unit) / l.rowPx); // lines a label covers, plus a pixel of air
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

/** Points of the curve for bin heights `ys`: one per bin centre, the ends carried to the edges. */
export function curvePoints(ys: ArrayLike<number>, width: number): { x: number; y: number }[] {
  const points = Array.from({ length: ys.length }, (_, i) => ({ x: ((hzOfBin(i) - loHz) / (hiHz - loHz)) * width, y: ys[i] }));
  return ys.length === 0 ? [] : [{ x: 0, y: ys[0] }, ...points, { x: width, y: ys[ys.length - 1] }];
}

/**
 * The plate behind a label in `slot`, around the text line `middle`, a pixel taller than the text.
 */
export function plateRect(slot: Slot, middle: number, l: Layout): Box {
  const h = l.text + 2 * l.unit;
  return { x: slot.x, y: middle - Math.round(h / 2), w: slot.w, h };
}

const CURVE_MEAN_LINES = 2 * LINES_PER_SECOND; // quiet shape: mean of the last two seconds, in dB
// bright line: mean of the last second, in power; a single line jumps about 5 dB between bins
const CURVE_NOW_LINES = LINES_PER_SECOND;

/**
 * The newest `count` of `lines` (newest first), none from before we last began or stopped sending.
 */
function newest<T extends { tx: boolean }>(lines: readonly T[], count: number): T[] {
  const other = lines.findIndex((line) => line.tx !== lines[0].tx);
  return lines.slice(0, Math.min(count, other < 0 ? lines.length : other));
}

/**
 * Quiet shape under the curve: mean in dB of the newest `count` lines (two seconds), leaving out
 * lines from before our own transmission changed, or a signal no longer there would linger for two
 * seconds.
 */
export function curveMean(lines: readonly { bytes: Uint8Array; tx: boolean }[], count = CURVE_MEAN_LINES): Float32Array {
  const last = newest(lines, count);
  return Float32Array.from({ length: BINS }, (_, i) => last.reduce((sum, line) => sum + line.bytes[i], 0) / Math.max(1, last.length));
}

/** Bright line of the curve: mean power of the last second's lines, with the same care. */
export function curveNow(lines: readonly { bytes: Uint8Array; tx: boolean }[], count = CURVE_NOW_LINES): Float32Array {
  return powerMean(newest(lines, count).map((line) => line.bytes));
}
