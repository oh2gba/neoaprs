// Canvas painter of the HF radio's waterfall: keeps a canvas up to date one line at a time from
// rows. The numbers are in waterfall.ts, the time axis in waterfalllines.ts. Colours are the page's
// --waterfall-* tokens (styles/tokens.css), the same in both themes.
import {
  PACE,
  colourTable,
  curveMean,
  curveNow,
  curvePoints,
  dbOfByte,
  layout,
  placeLabel,
  plateRect,
  rulerTicks,
  spread,
  timeText,
  xOfHz,
  type Layout,
  type Rgb,
  type Slot,
  type Speed,
} from "@/lib/waterfall";
import { Lines, type DrawnRow } from "@/lib/waterfalllines";
import { LIMITS } from "@/protocol/lists";

const { signalLoHz, signalHiHz } = LIMITS.scope;

/** A token colour as three channels; a token that is not `#rrggbb` is black. */
function channels(hex: string): Rgb {
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex.trim());
  return m ? [parseInt(m[1] ?? "0", 16), parseInt(m[2] ?? "0", 16), parseInt(m[3] ?? "0", 16)] : [0, 0, 0];
}

const hex = (c: Rgb): string => "#" + c.map((v) => Math.round(v).toString(16).padStart(2, "0")).join("");

// The curve's box runs from 8 dB under the floor to 32 dB over it, with a line every 10 dB.
// Anything stronger runs along the top.
const CURVE_DB = [-8, 32] as const;

const TIME_STRENGTH = 0.7; // times are fainter than calls: the calls are the news
const PLATE_STRENGTH = 0.7; // a label's plate is this much of the ground colour, so text reads over any signal
const GRID_STRENGTH = 0.5; // the curve's grid is this much of the ruler colour; the floor's line gets more
const FLOOR_STRENGTH = 0.8;
const SHAPE_STRENGTH = 0.4; // the mean's shape is this much of its colour, so it does not outshine the picture

/** What was heard, to be written on the line of the moment `at`. */
export interface HeardLabel {
  at: number;
  text: string;
}

/** Colours the painter draws with besides the scale, as CSS colours. */
type Inks = Record<"ground" | "shape" | "now" | "ink" | "quiet" | "grid" | "receive" | "transmit", string>;

/** What the painter draws with for the current canvas size. */
interface Look extends Inks {
  l: Layout;
  /**
   * Pixel height of a line at this speed and the number of lines shown, the last cut at the
   * picture's end.
   */
  linePx: number;
  shown: number;
  context: CanvasRenderingContext2D;
  /** Colour of every byte, and the pixels of one line, written a pixel at a time. */
  colours: Uint32Array;
  strip: ImageData;
  pixels: Uint32Array;
  font: string;
}

/**
 * Read the painter's colours from the tokens in effect on the canvas: --waterfall-0 to -4 for the
 * scale, then -rule, -ink, -grid, -rx and -tx. A missing token is drawn in the text colour.
 */
function lookOf(canvas: HTMLCanvasElement, context: CanvasRenderingContext2D, l: Layout, tall: number): Look {
  const style = getComputedStyle(canvas);
  const token = (name: string): string => style.getPropertyValue(`--waterfall-${name}`).trim() || "currentColor";
  const scale = [0, 1, 2, 3, 4].map((i) => channels(token(String(i))));
  const linePx = l.rowPx * tall;
  const strip = context.createImageData(l.width, linePx);
  return {
    l,
    linePx,
    shown: Math.ceil(l.rows / tall),
    context,
    colours: new Uint32Array(colourTable(scale).buffer),
    strip,
    pixels: new Uint32Array(strip.data.buffer),
    font: `${l.text}px ${style.fontFamily || "sans-serif"}`,
    ground: hex(scale[0]),
    shape: hex(scale[1]),
    now: hex(scale[3]),
    quiet: token("rule"),
    ink: token("ink"),
    grid: token("grid"),
    receive: token("rx"),
    transmit: token("tx"),
  };
}

/**
 * Painter of one canvas. Rows (each with its time) become lines of a fifth of a second; each
 * finished line is the new top line and older ones move down by copying the canvas onto itself, so
 * a line costs the same at any height. A line is either our own transmission or what was heard,
 * never both; time without rows is a gap. Every quarter minute a thin line with the time crosses
 * the picture; labels move down with it. Under the picture the last second's spectrum is a curve
 * over the floor's line, with the recent mean behind it. A resize redraws from the lines kept;
 * `show` draws the picture as it stood at a moment.
 */
export class Waterfall {
  private pace: (typeof PACE)[Speed];
  private book: Lines;
  // a label's row is its line number (see slotOf in waterfalllines.ts)
  private heard: { row: number; text: string }[] = [];
  private slots: Slot[] = [];
  private look: Look | null = null;

  constructor(
    private readonly canvas: HTMLCanvasElement,
    speed: Speed = "normal",
  ) {
    this.pace = PACE[speed];
    this.book = new Lines(this.pace.lineMs);
  }

  /**
   * Set another speed: kept lines and labels are dropped; the caller redraws from its rows with
   * `show`.
   */
  setSpeed(speed: Speed): void {
    this.pace = PACE[speed];
    this.book = new Lines(this.pace.lineMs);
    [this.heard, this.slots, this.look] = [[], [], null];
  }

  /** The number of the line the moment `at` falls in, at this speed. */
  slot(at: number): number {
    return this.book.slot(at);
  }

  /** Add a row: its bytes, its time (ms, page clock), and whether it is our own transmission. */
  push(bytes: Uint8Array, at: number, tx: boolean): void {
    const was = this.book.sending;
    const added = this.book.add({ bytes, at, tx });
    this.forgetOld();
    const before = this.look;
    const look = this.fit();
    if (!look) return;
    if (look !== before) return this.paint(look);
    if (this.book.sending !== was) this.drawRuler(look);
    if (added === 0) return;
    const { x, y, w, h } = look.l.picture;
    const down = added * look.linePx;
    if (h > down) look.context.drawImage(this.canvas, x, y, w, h - down, x, y + down, w, h - down);
    this.blankUnkept(look);
    for (let depth = Math.min(added, look.shown) - 1; depth >= 0; depth--) this.drawRow(look, depth);
    const top = this.book.top;
    for (const label of this.heard) if (label.row > top - added && label.row <= top) this.drawLabel(look, label);
    this.drawCurve(look);
  }

  /**
   * Write what was heard at `at` on that moment's line: now if it is drawn already, else when it
   * is.
   */
  label(text: string, at: number): void {
    const label = { row: this.book.slot(at), text };
    this.heard.push(label);
    if (this.look && label.row <= this.book.top) this.drawLabel(this.look, label);
  }

  /** Draw the picture as it stands at `now` from these rows (oldest first) and labels. */
  show(rows: readonly DrawnRow[], labels: readonly HeardLabel[], now: number): void {
    this.book.build(rows, now);
    this.heard = labels.map((label) => ({ row: this.book.slot(label.at), text: label.text }));
    this.forgetOld();
    this.draw();
  }

  /** Forget every row; the picture starts again. */
  clear(): void {
    this.show([], [], 0);
  }

  /** Redraw everything from what is kept (new canvas size or new token colours). */
  draw(): void {
    this.look = null;
    const look = this.fit();
    if (look) this.paint(look);
  }

  /** Drop the labels older than the lines kept. */
  private forgetOld(): void {
    const oldest = this.book.top - this.book.kept;
    this.heard = this.heard.filter((label) => label.row > oldest);
    this.slots = this.slots.filter((slot) => slot.row > oldest);
  }

  private paint(look: Look): void {
    const { context, l } = look;
    context.fillStyle = look.ground;
    context.fillRect(0, 0, l.width, l.height);
    for (let depth = Math.min(look.shown, this.book.lines.length) - 1; depth >= 0; depth--) this.drawRow(look, depth);
    this.slots = [];
    const top = this.book.top;
    for (const label of this.heard) if (label.row <= top) this.drawLabel(look, label);
    this.drawRuler(look);
    this.drawCurve(look);
  }

  /**
   * What to draw with for the current canvas size: the same while the size is, else a new one
   * (canvas resized and emptied). Null when the canvas cannot be drawn on or has no room.
   */
  private fit(): Look | null {
    const [width, height] = [this.canvas.clientWidth, this.canvas.clientHeight];
    // not shown (closed fold): draw nothing until it has room
    if (width === 0 || height === 0) return (this.look = null);
    const l = layout(width, height, window.devicePixelRatio || 1);
    if (this.look && this.look.l.width === l.width && this.look.l.height === l.height) return this.look;
    const context = this.canvas.getContext("2d");
    if (!context) return null;
    [this.canvas.width, this.canvas.height] = [l.width, l.height];
    this.look = lookOf(this.canvas, context, l, this.pace.tall);
    return this.look;
  }

  /**
   * Pixels of the picture, from its top, that the lines kept can fill; at Slow they may end above
   * the bottom.
   */
  private keptPx(look: Look): number {
    return Math.min(look.l.picture.h, this.book.kept * look.linePx);
  }

  /**
   * Below the lines kept the picture is ground: what the copy down moved there is older than two
   * minutes.
   */
  private blankUnkept(look: Look): void {
    const { picture } = look.l;
    const kept = this.keptPx(look);
    if (kept >= picture.h) return;
    look.context.fillStyle = look.ground;
    look.context.fillRect(picture.x, picture.y + kept, picture.w, picture.h - kept);
  }

  /**
   * Write text on the picture with room from line `y` down. Each letter has a dark edge in the
   * ground colour and a label has a plate behind it (`plate`: its width, air at the sides
   * included). Nothing falls outside the picture.
   */
  private write(look: Look, text: string, x: number, y: number, colour: string, strength = 1, plate = 0): void {
    const { context, l } = look;
    const [left, middle] = [x + 3 * l.unit, y + Math.round((l.plate + l.unit) / 2)];
    context.save();
    context.beginPath();
    context.rect(l.picture.x, l.picture.y, l.picture.w, this.keptPx(look));
    context.clip();
    if (plate > 0) {
      const { x: plateX, y: plateY, w, h } = plateRect({ row: 0, x, w: plate }, middle, l);
      context.globalAlpha = PLATE_STRENGTH;
      context.fillStyle = look.ground;
      context.beginPath();
      if (context.roundRect) context.roundRect(plateX, plateY, w, h, 2 * l.unit);
      else context.rect(plateX, plateY, w, h);
      context.fill();
      context.globalAlpha = 1;
    }
    context.font = look.font;
    context.textBaseline = "middle";
    context.textAlign = "left";
    context.lineJoin = "round";
    context.lineWidth = 3 * l.unit;
    context.strokeStyle = look.ground;
    context.strokeText(text, left, middle);
    context.globalAlpha = strength;
    context.fillStyle = colour;
    context.fillText(text, left, middle);
    context.restore();
  }

  /**
   * The line `n` lines down from the top: its pixels, the transmit strip, and on a quarter-minute
   * line a thin rule at its top with the time under it at the left edge. A line that does not fit
   * at the bottom is cut.
   */
  private drawRow(look: Look, depth: number): void {
    const { context, l, colours, pixels, linePx } = look;
    const row = this.book.lines[depth];
    const y = l.picture.y + depth * linePx;
    // the whole line, or what is left of it where the picture ends
    const high = Math.min(linePx, l.picture.y + l.picture.h - y);
    if (row.bytes === null) pixels.fill(colours[0], 0, l.width);
    else {
      const values = spread(row.bytes, l.width);
      for (let x = 0; x < l.width; x++) pixels[x] = colours[Math.round(values[x])];
    }
    for (let line = 1; line < linePx; line++) pixels.copyWithin(line * l.width, 0, l.width);
    if (high < linePx) context.putImageData(look.strip, l.picture.x, y, 0, 0, l.width, high);
    else context.putImageData(look.strip, l.picture.x, y);
    context.fillStyle = look.transmit;
    if (row.tx) context.fillRect(0, y, 3 * l.unit, high);
    if (row.quarter === null) return;
    context.fillStyle = look.grid;
    context.fillRect(0, y, l.width, Math.min(l.rowPx, high));
    this.write(look, timeText(row.quarter), 5 * l.unit, y + linePx, look.ink, TIME_STRENGTH);
  }

  /** The layout in units of lines at this speed, for placing labels. */
  private labelLayout(look: Look): Layout {
    return { ...look.l, rowPx: look.linePx, rows: look.shown };
  }

  private drawLabel(look: Look, label: { row: number; text: string }): void {
    look.context.font = look.font;
    // three pixels of air on each side
    const w = Math.ceil(look.context.measureText(label.text).width) + 6 * look.l.unit;
    const slot = placeLabel(label.row, w, this.slots, this.labelLayout(look));
    if (!slot) return;
    this.slots.push(slot);
    this.write(look, label.text, slot.x, look.l.picture.y + (this.book.top - slot.row) * look.linePx, look.ink, 1, w);
  }

  /**
   * The ruler: a tick every 100 Hz, numbers over the long ones, and the band of a frame as a
   * bracket (transmit colour while sending).
   */
  private drawRuler(look: Look): void {
    const { context, l } = look;
    const { w, h } = l.ruler;
    context.fillStyle = look.ground;
    context.fillRect(0, 0, w, h);
    context.font = look.font;
    context.textBaseline = "top";
    context.textAlign = "center";
    for (const tick of rulerTicks(w, 4 * l.text)) {
      const long = tick.hz % 500 === 0;
      context.fillStyle = look.quiet;
      context.fillRect(tick.x, h - (long ? 8 : 4) * l.unit, l.unit, (long ? 8 : 4) * l.unit);
      context.fillStyle = look.ink;
      if (tick.numbered) context.fillText(String(tick.hz), tick.x, 2 * l.unit);
    }
    const [from, to] = [xOfHz(signalLoHz, w), xOfHz(signalHiHz, w)];
    context.fillStyle = this.book.sending ? look.transmit : look.receive;
    context.fillRect(from, h - 2 * l.unit, to - from, 2 * l.unit);
    for (const x of [from, to - 2 * l.unit]) context.fillRect(x, h - 6 * l.unit, 2 * l.unit, 6 * l.unit);
  }

  /**
   * The curve under the picture: a faint dotted grid (every 10 dB and 500 Hz), the mean shape, the
   * floor's level line, and the last second's spectrum as a bright line one CSS pixel thick.
   */
  private drawCurve(look: Look): void {
    const { context, l } = look;
    const { x, y, w, h } = l.curve;
    const yOf = (db: number): number =>
      y + Math.round((1 - (Math.max(CURVE_DB[0], Math.min(CURVE_DB[1], db)) - CURVE_DB[0]) / (CURVE_DB[1] - CURVE_DB[0])) * (h - l.unit));
    context.fillStyle = look.ground;
    context.fillRect(x, y - l.unit, w, h + l.unit);
    context.fillStyle = look.grid;
    context.fillRect(x, y - l.unit, w, l.unit);
    // The dotted grid is one path of dashes, each line through the middle of its pixels.
    const half = l.unit / 2;
    const levels = [10, 20, 30].map((db) => [x, yOf(db) + half, x + w, yOf(db) + half]);
    const posts = rulerTicks(w, 0).flatMap((tick) => (tick.numbered ? [[tick.x + half, y, tick.x + half, y + h]] : []));
    context.strokeStyle = look.quiet;
    context.globalAlpha = GRID_STRENGTH;
    context.lineWidth = l.unit;
    context.setLineDash([l.unit, 3 * l.unit]);
    context.beginPath();
    for (const [fromX, fromY, toX, toY] of [...levels, ...posts]) {
      context.moveTo(fromX, fromY);
      context.lineTo(toX, toY);
    }
    context.stroke();
    context.setLineDash([]);
    context.globalAlpha = 1;
    // Shape and line pass through the middle of the pixels, from bin centre to bin centre.
    // The shape covers the last two seconds and the bright line the last second, at every speed.
    const [meanCount, nowCount] = [2000, 1000].map((ms) => Math.round(ms / this.book.lineMs));
    const lines = this.book.newest(meanCount) as { bytes: Uint8Array; tx: boolean }[];
    const [average, now] = [curveMean(lines, meanCount), curveNow(lines, nowCount)].map((bytes) =>
      curvePoints(
        Array.from(bytes, (byte) => yOf(dbOfByte(byte)) + half),
        w,
      ),
    );
    context.globalAlpha = SHAPE_STRENGTH; // before the first line the shape is the box's lowest line
    context.fillStyle = look.shape;
    context.beginPath();
    context.moveTo(0, y + h);
    for (const point of average) context.lineTo(point.x, point.y);
    context.lineTo(w, y + h);
    context.closePath();
    context.fill();
    context.globalAlpha = FLOOR_STRENGTH;
    context.fillStyle = look.quiet;
    context.fillRect(x, yOf(0), w, l.unit);
    context.globalAlpha = 1;
    if (lines.length === 0) return;
    context.strokeStyle = look.now;
    context.lineWidth = l.unit;
    context.lineJoin = "round";
    context.beginPath();
    now.forEach((point, i) => (i === 0 ? context.moveTo(point.x, point.y) : context.lineTo(point.x, point.y)));
    context.stroke();
  }
}
