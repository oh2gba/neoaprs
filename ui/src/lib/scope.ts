// The HF radio's scope, the parts that are not a component: where the frame's signal band is among the bins, the zones of the receive level, the gain and the peak as text, how a picture eases toward the next, and the drawing of the
// spectrum on a canvas. Every number (the bins, the band, the zones) is the daemon's, through LIMITS (neoaprs/mercuryscope.py).
import { LIMITS } from "@/protocol/lists";

const { bins: BINS, loHz, hiHz, signalLoHz, signalHiHz, levelMinDbfs, levelMaxDbfs, levelGoodDbfs, peakClipDbfs } = LIMITS.scope;
const BIN_HZ = (hiHz - loHz) / BINS;

/** The first and the one past the last bin of the signal band of a frame (1.2 to 1.8 kHz above the dial). */
export const SIGNAL_BINS: readonly [number, number] = [Math.round((signalLoHz - loHz) / BIN_HZ), Math.round((signalHiHz - loHz) / BIN_HZ)];
/** How tall the spectrum is drawn, in dB over the floor: a signal taller than this is cut off at the top. */
export const DRAW_RANGE_DB = 40;
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

/** One step of the ease from the picture shown toward the one told: a part of the way each time, and the end itself when it is within half a dB (so that it comes to rest). Returns the new values and whether any is still moving. */
export function ease(shown: readonly number[], target: readonly number[], part = 0.3): { values: number[]; moving: boolean } {
  let moving = false;
  const values = target.map((to, i) => {
    const from = shown[i] ?? to;
    const gap = to - from;
    if (Math.abs(gap) < 0.5) return to;
    moving = true;
    return from + gap * part;
  });
  return { values, moving };
}

/** The colours the spectrum is drawn with, read from the page's tokens. */
export interface ScopeColours {
  line: string;
  wash: string;
  band: string;
  grid: string;
}

/** Reads the colours of the spectrum from the tokens of the page (styles/tokens.css) in effect on `element`: the accent for what is received, the warning colour for our own transmission. */
export function scopeColours(element: Element, transmitting: boolean): ScopeColours {
  const style = getComputedStyle(element);
  const token = (name: string): string => style.getPropertyValue(name).trim() || "currentColor";
  return {
    line: token(transmitting ? "--warn" : "--accent"),
    wash: token(transmitting ? "--warn-soft-bg" : "--accent-soft-bg"),
    band: token("--accent-soft-bg"),
    grid: token("--border"),
  };
}

/** Draws the spectrum on the canvas: the signal band of a frame as a faint block, a line of dotted rules every 10 dB, and the bins as a filled line over the floor. `heights` are dB over the floor, one for each bin. */
export function drawScope(canvas: HTMLCanvasElement, heights: readonly number[], colours: ScopeColours): void {
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.round(canvas.clientWidth * ratio));
  const height = Math.max(1, Math.round(canvas.clientHeight * ratio));
  if (canvas.width !== width) canvas.width = width;
  if (canvas.height !== height) canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) return;
  context.clearRect(0, 0, width, height);
  const step = width / BINS;
  const base = height - 1;
  const top = (db: number): number => base - (Math.min(DRAW_RANGE_DB, Math.max(0, db)) / DRAW_RANGE_DB) * (base - 2);
  context.fillStyle = colours.band;
  context.globalAlpha = 0.5;
  context.fillRect(SIGNAL_BINS[0] * step, 0, (SIGNAL_BINS[1] - SIGNAL_BINS[0]) * step, height);
  context.globalAlpha = 1;
  context.strokeStyle = colours.grid;
  context.lineWidth = ratio;
  context.setLineDash([2 * ratio, 3 * ratio]);
  for (let db = 10; db < DRAW_RANGE_DB; db += 10) {
    context.beginPath();
    context.moveTo(0, top(db));
    context.lineTo(width, top(db));
    context.stroke();
  }
  context.setLineDash([]);
  context.beginPath();
  context.moveTo(0, base);
  heights.forEach((h, i) => context.lineTo((i + 0.5) * step, top(h)));
  context.lineTo(width, base);
  context.closePath();
  context.fillStyle = colours.wash;
  context.fill();
  context.strokeStyle = colours.line;
  context.lineWidth = 1.5 * ratio;
  context.lineJoin = "round";
  context.beginPath();
  heights.forEach((h, i) => (i === 0 ? context.moveTo(0.5 * step, top(h)) : context.lineTo((i + 0.5) * step, top(h))));
  context.stroke();
}
