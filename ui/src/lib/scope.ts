// The HF radio's scope, the parts that are not a component: where the frame's signal band is among the bins, the zones of the receive level, the gain and the peak as text, the rows of the waterfall kept from the pictures, and the
// drawing of the waterfall on a canvas. Every number (the bins, the band, the zones) is the daemon's, through LIMITS (neoaprs/mercuryscope.py).
import { LIMITS } from "@/protocol/lists";

const { bins: BINS, loHz, hiHz, signalLoHz, signalHiHz, levelMinDbfs, levelMaxDbfs, levelGoodDbfs, peakClipDbfs } = LIMITS.scope;
const BIN_HZ = (hiHz - loHz) / BINS;

/** The first and the one past the last bin of the signal band of a frame (1.2 to 1.8 kHz above the dial). */
export const SIGNAL_BINS: readonly [number, number] = [Math.round((signalLoHz - loHz) / BIN_HZ), Math.round((signalHiHz - loHz) / BIN_HZ)];
/** How strong a bin is drawn in full colour, in dB over the floor: a stronger one is drawn the same. */
export const DRAW_RANGE_DB = 30;
/** How tall a row of the waterfall is, in CSS pixels: one picture (a fifth of a second), so that the 72 pixels of the box hold the last seven seconds or so. */
export const ROW_PX = 2;
/** How many rows are kept: more than the box shows, so that a taller one would be filled too. */
export const KEPT_ROWS = 64;
export const SCOPE_BINS = BINS;

export type Zone = "low" | "good" | "high" | "clip";

/** The zone of a receive level in dBFS: under the good range (too little audio for the modem to work with), in it, over it, and near full scale, where the sound card clips. */
export function levelZone(level: number): Zone {
  if (level < levelGoodDbfs[0]) return "low";
  if (level <= levelGoodDbfs[1]) return "good";
  return level < -10 ? "high" : "clip";
}

/** Where a level is on the bar, 0 to 100 percent. */
export function levelPercent(level: number): number {
  const span = levelMaxDbfs - levelMinDbfs;
  return Math.max(0, Math.min(100, ((level - levelMinDbfs) / span) * 100));
}

/** The good range as the parts of the bar it covers, in percent from the left: [from, to]. */
export const GOOD_PERCENT: readonly [number, number] = [levelPercent(levelGoodDbfs[0]), levelPercent(levelGoodDbfs[1])];

/** A level or a peak as the number the page shows, "-38"; the minus is the one of the keyboard (the same in every language); null (nothing yet) is a dash. */
export function dbText(value: number | null): string {
  return value === null ? "–" : String(value);
}

/** A gain as the number on the Transmit level control: "+3", "0", "-6". */
export function gainText(db: number): string {
  return db > 0 ? `+${db}` : String(db);
}

/** Whether a transmission peaking at this many dBFS clips in the sound card. */
export const clips = (peak: number | null): boolean => peak !== null && peak >= peakClipDbfs;

/** One row of the waterfall: the bins of a picture, in dB over the floor, and whether it is of our own transmission. */
export interface Row {
  bins: readonly number[];
  tx: boolean;
}

/** The rows with a new one on top, the newest first, and the oldest let go past `keep`. */
export function addRow(rows: readonly Row[], row: Row, keep = KEPT_ROWS): Row[] {
  return [row, ...rows.slice(0, Math.max(0, keep - 1))];
}

/** How strongly a bin is drawn, 0 (the floor, nothing) to 1 (DRAW_RANGE_DB over it and more), its place on the colour scale: a little more than in proportion at the weak end, so that a weak frame shows over the noise. */
export function strength(db: number): number {
  return Math.pow(Math.min(DRAW_RANGE_DB, Math.max(0, db)) / DRAW_RANGE_DB, 0.75);
}

/** The colour scale of the waterfall, the way a rig's waterfall looks: navy at the floor (the background), then blue, cyan, yellow and red as a bin rises over it, by strength 0 to 1. Fixed, not the
 * page's tokens: the picture is dark in the light theme too, as on a rig, so that the weak signals show. */
export const HEAT: readonly (readonly [number, readonly [number, number, number]])[] = [
  [0, [0, 8, 40]],
  [0.25, [8, 52, 190]],
  [0.5, [0, 170, 255]],
  [0.75, [255, 226, 0]],
  [1, [255, 40, 16]],
];
/** The frame's band over the picture, and its two dotted rules: light, on the dark picture. */
const BAND = "rgba(255, 255, 255, 0.07)";
const RULE = "rgba(255, 255, 255, 0.45)";

/** The colour of a received bin of strength 0 to 1 on the scale, as `rgb(r, g, b)`. */
export function heat(s: number): string {
  const x = Math.min(1, Math.max(0, s));
  const upper = HEAT.findIndex(([at]) => at >= x);
  const [hiAt, hi] = HEAT[Math.max(0, upper)];
  const [loAt, lo] = HEAT[Math.max(0, upper - 1)];
  const f = hiAt === loAt ? 0 : (x - loAt) / (hiAt - loAt);
  const mix = (i: number): number => Math.round(lo[i] + (hi[i] - lo[i]) * f);
  return `rgb(${mix(0)}, ${mix(1)}, ${mix(2)})`;
}

/** The colour of a bin of our own transmission of strength 0 to 1: grey to white, apart from the scale of what is received. */
export function sentHeat(s: number): string {
  const v = Math.round(40 + 195 * Math.min(1, Math.max(0, s)));
  return `rgb(${v}, ${v}, ${v})`;
}

/** Draws the waterfall on the canvas: the background at the floor's colour, the rows, the newest at the top, each bin a cell in the colour of its strength (a bin at the floor is left as the background), and the
 * signal band of a frame as a faint block between two dotted rules over them. */
export function drawWaterfall(canvas: HTMLCanvasElement, rows: readonly Row[]): void {
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.round(canvas.clientWidth * ratio));
  const height = Math.max(1, Math.round(canvas.clientHeight * ratio));
  if (canvas.width !== width) canvas.width = width;
  if (canvas.height !== height) canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) return;
  context.clearRect(0, 0, width, height);
  context.fillStyle = heat(0);
  context.fillRect(0, 0, width, height);
  const step = width / BINS;
  const edge = (bin: number): number => Math.round(bin * step);
  const [bandFrom, bandTo] = [edge(SIGNAL_BINS[0]), edge(SIGNAL_BINS[1])];
  const rowHeight = ROW_PX * ratio;
  for (let r = 0; r < rows.length; r++) {
    const top = Math.round(r * rowHeight);
    if (top >= height) break;
    const bottom = Math.min(height, Math.round((r + 1) * rowHeight));
    const row = rows[r];
    for (let b = 0; b < BINS; b++) {
      const s = strength(row.bins[b] ?? 0);
      if (s < 0.03) continue;
      context.fillStyle = row.tx ? sentHeat(s) : heat(s);
      context.fillRect(edge(b), top, edge(b + 1) - edge(b), bottom - top);
    }
  }
  context.fillStyle = BAND;
  context.fillRect(bandFrom, 0, bandTo - bandFrom, height);
  context.strokeStyle = RULE;
  context.lineWidth = ratio;
  context.setLineDash([2 * ratio, 3 * ratio]);
  for (const x of [bandFrom, bandTo]) {
    context.beginPath();
    context.moveTo(x + ratio / 2, 0);
    context.lineTo(x + ratio / 2, height);
    context.stroke();
  }
  context.setLineDash([]);
}
