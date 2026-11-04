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

type Rgb = readonly [number, number, number];

/** The colours of the waterfall, the page's --waterfall-* tokens (styles/tokens.css): a rig's colour scale from the floor (also the background) to the strongest, the two ends of our own transmission (grey to
 * white, apart from the scale), the faint block where a frame sits and its dotted edges. The same in both themes: the picture is dark in the light theme too, as on a rig, so that the weak signals show. */
export interface WaterfallColours {
  scale: readonly Rgb[];
  sent: readonly [Rgb, Rgb];
  band: string;
  rule: string;
}

/** A colour of the tokens as its three channels; a token that is not `#rrggbb` is black. */
function channels(hex: string): Rgb {
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex.trim());
  return m ? [parseInt(m[1] ?? "0", 16), parseInt(m[2] ?? "0", 16), parseInt(m[3] ?? "0", 16)] : [0, 0, 0];
}

/** Reads the colours of the waterfall from the tokens in effect on `element`. */
export function waterfallColours(element: Element): WaterfallColours {
  const style = getComputedStyle(element);
  const token = (name: string): string => style.getPropertyValue(name).trim();
  return {
    scale: [0, 1, 2, 3, 4].map((i) => channels(token(`--waterfall-${i}`))),
    sent: [channels(token("--waterfall-sent-0")), channels(token("--waterfall-sent-1"))],
    band: token("--waterfall-band") || "transparent",
    rule: token("--waterfall-rule") || "currentColor",
  };
}

const hex = (c: Rgb): string => "#" + c.map((v) => Math.round(v).toString(16).padStart(2, "0")).join("");
const between = (lo: Rgb, hi: Rgb, f: number): Rgb => [lo[0] + (hi[0] - lo[0]) * f, lo[1] + (hi[1] - lo[1]) * f, lo[2] + (hi[2] - lo[2]) * f];

/** The colour of a bin of strength 0 to 1 on a scale of colours spaced evenly from 0 to 1, as `#rrggbb`. */
export function heat(s: number, scale: readonly Rgb[]): string {
  if (scale.length === 0) return hex([0, 0, 0]);
  const x = Math.min(1, Math.max(0, s)) * (scale.length - 1);
  const i = Math.min(scale.length - 2, Math.floor(x));
  return scale.length === 1 ? hex(scale[0] as Rgb) : hex(between(scale[i] as Rgb, scale[i + 1] as Rgb, x - i));
}

/** Draws the waterfall on the canvas: the background at the floor's colour, the rows, the newest at the top, each bin a cell in the colour of its strength (a bin at the floor is left as the background), and the
 * signal band of a frame as a faint block between two dotted rules over them. */
export function drawWaterfall(canvas: HTMLCanvasElement, rows: readonly Row[], colours: WaterfallColours): void {
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.round(canvas.clientWidth * ratio));
  const height = Math.max(1, Math.round(canvas.clientHeight * ratio));
  if (canvas.width !== width) canvas.width = width;
  if (canvas.height !== height) canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) return;
  context.clearRect(0, 0, width, height);
  context.fillStyle = heat(0, colours.scale);
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
      context.fillStyle = row.tx ? heat(s, colours.sent) : heat(s, colours.scale);
      context.fillRect(edge(b), top, edge(b + 1) - edge(b), bottom - top);
    }
  }
  context.fillStyle = colours.band;
  context.fillRect(bandFrom, 0, bandTo - bandFrom, height);
  context.strokeStyle = colours.rule;
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
