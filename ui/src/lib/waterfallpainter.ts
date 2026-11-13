// The painter of the HF radio's waterfall: it keeps a canvas up to date one line at a time from the rows it is given (lib/waterfall.ts has the numbers it draws by: the lines, the colours, the layout, the ruler, the labels
// and the curve). The colours are the page's --waterfall-* tokens (styles/tokens.css), the same in both themes.
import {
  KEPT_LINES,
  ROWS_PER_LINE,
  colourTable,
  curveMean,
  curveNow,
  curvePoints,
  dbOfByte,
  layout,
  lineOf,
  placeLabel,
  plateRect,
  rulerTicks,
  silentOwn,
  spread,
  startsQuarter,
  timeText,
  xOfHz,
  type Layout,
  type Rgb,
  type Slot,
} from "@/lib/waterfall";
import { LIMITS } from "@/protocol/lists";

const { signalLoHz, signalHiHz } = LIMITS.scope;

/** A colour of the tokens as its three channels; a token that is not `#rrggbb` is black. */
function channels(hex: string): Rgb {
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex.trim());
  return m ? [parseInt(m[1] ?? "0", 16), parseInt(m[2] ?? "0", 16), parseInt(m[3] ?? "0", 16)] : [0, 0, 0];
}

/** A colour of the scale as CSS writes it. */
const hex = (c: Rgb): string => "#" + c.map((v) => Math.round(v).toString(16).padStart(2, "0")).join("");

// The curve's box reaches from 8 dB under the floor, deeper than the bright line dips, to 32 dB over it, where a strong station stands, with a line every 10 dB; what is stronger runs along the top.
const CURVE_DB = [-8, 32] as const;

const TIME_STRENGTH = 0.7; // the time is written this much fainter than what was heard: it is the scale, the calls are the news
const PLATE_STRENGTH = 0.7; // a label's plate is the ground's colour this much: the picture shows through it, and the text is plain over any signal
const GRID_STRENGTH = 0.5; // the grid of the curve is the ruler's colour this much, and the floor's line (the one level that matters) this much more
const FLOOR_STRENGTH = 0.8;
const SHAPE_STRENGTH = 0.4; // the shape of the mean is this much of its colour over the ground: it stands behind the bright line and does not outshine the picture above

interface Kept {
  bytes: Uint8Array;
  at: number;
  tx: boolean;
  time: boolean;
}

/** The colours the painter draws with beside the scale, each as CSS writes a colour. */
type Inks = Record<"ground" | "shape" | "now" | "ink" | "quiet" | "grid" | "receive" | "transmit", string>;

/** What the painter draws with for the size the canvas has now. */
interface Look extends Inks {
  l: Layout;
  context: CanvasRenderingContext2D;
  /** The colour of every byte and the pixels of one line of the picture, each pixel one number: a line is written a pixel at a go. */
  colours: Uint32Array;
  strip: ImageData;
  pixels: Uint32Array;
  font: string;
}

/** Reads what the painter draws with from the tokens in effect on the canvas (styles/tokens.css): the five colours of the scale (--waterfall-0 to -4, the ground the first), the ticks of the ruler (-rule), the bright
 * text (-ink), the grid (-grid) and the colours of receive and transmit (-rx, -tx). A token that is not there is drawn in the colour of the text. */
function lookOf(canvas: HTMLCanvasElement, context: CanvasRenderingContext2D, l: Layout): Look {
  const style = getComputedStyle(canvas);
  const token = (name: string): string => style.getPropertyValue(`--waterfall-${name}`).trim() || "currentColor";
  const scale = [0, 1, 2, 3, 4].map((i) => channels(token(String(i))));
  const strip = context.createImageData(l.width, l.rowPx);
  return {
    l,
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

/** The painter of one canvas. It is given rows (Floor.over made them); every ROWS_PER_LINE of them become a line, which is the new top line of the picture: what is there is moved down by a copy of the canvas onto itself and
 * the new line is written as pixels, so a line costs the same however high the box is. A line is either of our own transmission or of what is heard, never of both: when we begin or stop sending, the line that was being
 * gathered ends there, and a row of ours with nothing in it is not drawn at all, so a transmission has clean edges. On the first line of every quarter of a minute a thin line goes across with the time at the left edge, our own
 * transmission is a strip along that edge, and what was heard is written beside the band on the line its frame ended; all of it moves down with the picture. Under the picture the spectrum of the last second is a curve
 * over the floor's line, with the mean of the last seconds as a quiet shape behind it. When the canvas changes size everything is drawn again from the lines kept. */
export class Waterfall {
  private lines: Kept[] = []; // the newest first
  private open: Uint8Array[] = []; // the rows of the line that is being gathered...
  private waiting: string[] = []; // ...and what was heard on them: written when they are a line
  private sending = false;
  private at = 0; // the time of the newest row
  private heard: { row: number; text: string }[] = [];
  private slots: Slot[] = [];
  private count = 0; // the lines there have been: the number of the newest
  private look: Look | null = null;

  constructor(private readonly canvas: HTMLCanvasElement) {}

  /** A new row: its bytes (Floor.over), its time in milliseconds, and whether it is of our own transmission. */
  push(bytes: Uint8Array, at: number, tx: boolean): void {
    const turned = tx !== this.sending;
    let added = turned ? this.close() : 0;
    [this.sending, this.at] = [tx, at];
    if (!tx || !silentOwn(bytes)) this.open.push(bytes);
    if (this.open.length >= ROWS_PER_LINE) added += this.close();
    const before = this.look;
    const look = this.fit();
    if (!look) return;
    if (look !== before) return this.paint(look);
    if (turned) this.drawRuler(look);
    if (added === 0) return;
    const { x, y, w, h } = look.l.picture;
    const down = added * look.l.rowPx;
    if (h > down) look.context.drawImage(this.canvas, x, y, w, h - down, x, y + down, w, h - down);
    for (let depth = Math.min(added, look.l.rows) - 1; depth >= 0; depth--) this.drawRow(look, depth);
    for (const label of this.heard) if (label.row > this.count - added) this.drawLabel(look, label);
    this.drawCurve(look);
  }

  /** The rows gathered become a line, with what was heard on them; says how many lines that made (none where no row was gathered). */
  private close(): number {
    if (this.open.length === 0) return 0;
    const time = this.lines.length > 0 && startsQuarter(this.lines[0].at, this.at);
    this.count++;
    this.lines = [{ bytes: lineOf(this.open, this.sending), at: this.at, tx: this.sending, time }, ...this.lines.slice(0, KEPT_LINES - 1)];
    this.heard = [...this.heard, ...this.waiting.map((text) => ({ row: this.count, text }))].filter((label) => this.count - label.row < KEPT_LINES);
    this.slots = this.slots.filter((slot) => this.count - slot.row < KEPT_LINES);
    [this.open, this.waiting] = [[], []];
    return 1;
  }

  /** What was heard, written on the line the newest row is of: the frame ended there. */
  label(text: string): void {
    if (this.open.length > 0) return void this.waiting.push(text);
    if (this.lines.length === 0) return;
    const label = { row: this.count, text };
    this.heard.push(label);
    if (this.look) this.drawLabel(this.look, label);
  }

  /** Forgets every row: the picture starts again. */
  clear(): void {
    [this.lines, this.open, this.waiting, this.heard, this.slots, this.count, this.sending] = [[], [], [], [], [], 0, false];
    this.draw();
  }

  /** Draws everything again from what is kept: the canvas has a new size, or the tokens have other colours. */
  draw(): void {
    this.look = null;
    const look = this.fit();
    if (look) this.paint(look);
  }

  private paint(look: Look): void {
    const { context, l } = look;
    context.fillStyle = look.ground;
    context.fillRect(0, 0, l.width, l.height);
    for (let depth = Math.min(l.rows, this.lines.length) - 1; depth >= 0; depth--) this.drawRow(look, depth);
    this.slots = [];
    for (const label of this.heard) this.drawLabel(look, label);
    this.drawRuler(look);
    this.drawCurve(look);
  }

  /** What to draw with for the room the canvas has on this screen now: the same as before while its size is, and a new one (the canvas made that many pixels, and empty) when it changed. Null for a canvas that cannot be drawn on and for one
   * that has no room. */
  private fit(): Look | null {
    const [width, height] = [this.canvas.clientWidth, this.canvas.clientHeight];
    if (width === 0 || height === 0) return (this.look = null); // (a canvas that is not shown, in a fold that is closed: nothing is drawn, and all of it is when it has room again)
    const l = layout(width, height, window.devicePixelRatio || 1);
    if (this.look && this.look.l.width === l.width && this.look.l.height === l.height) return this.look;
    const context = this.canvas.getContext("2d");
    if (!context) return null;
    [this.canvas.width, this.canvas.height] = [l.width, l.height];
    this.look = lookOf(this.canvas, context, l);
    return this.look;
  }

  /** A text on the picture, its room from the line `y` down: each letter has a dark edge of the ground's colour round it and nothing else is covered, so that it reads over any picture and a label has a plate of the ground's colour behind it (`plate`: its width, the air at the sides included). Nothing of it falls outside the picture: a text on a line near the bottom ends where the picture does. */
  private write(look: Look, text: string, x: number, y: number, colour: string, strength = 1, plate = 0): void {
    const { context, l } = look;
    const [left, middle] = [x + 3 * l.unit, y + Math.round((l.plate + l.unit) / 2)];
    context.save();
    context.beginPath();
    context.rect(l.picture.x, l.picture.y, l.picture.w, l.picture.h);
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

  /** The line so many lines down from the top: its pixels, the strip of a transmission, and on the first of a quarter of a minute a thin line across with the time under it at the left edge. */
  private drawRow(look: Look, depth: number): void {
    const { context, l, colours, pixels } = look;
    const row = this.lines[depth];
    const y = l.picture.y + depth * l.rowPx;
    const values = spread(row.bytes, l.width);
    for (let x = 0; x < l.width; x++) pixels[x] = colours[Math.round(values[x])];
    for (let line = 1; line < l.rowPx; line++) pixels.copyWithin(line * l.width, 0, l.width);
    context.putImageData(look.strip, l.picture.x, y);
    context.fillStyle = look.transmit;
    if (row.tx) context.fillRect(0, y, 3 * l.unit, l.rowPx);
    if (!row.time) return;
    context.fillStyle = look.grid;
    context.fillRect(0, y, l.width, l.rowPx);
    this.write(look, timeText(row.at), 5 * l.unit, y + l.rowPx, look.ink, TIME_STRENGTH);
  }

  private drawLabel(look: Look, label: { row: number; text: string }): void {
    look.context.font = look.font;
    const w = Math.ceil(look.context.measureText(label.text).width) + 6 * look.l.unit; // (three pixels of air on each side)
    const slot = placeLabel(label.row, w, this.slots, look.l);
    if (!slot) return;
    this.slots.push(slot);
    this.write(look, label.text, slot.x, look.l.picture.y + (this.count - slot.row) * look.l.rowPx, look.ink, 1, w);
  }

  /** The ruler: a tick every 100 Hz hanging from its lower edge, the numbers over the long ones, and the band of a frame as a bracket on that edge, in the colour of receive, and of transmit while we send. */
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
    context.fillStyle = this.sending ? look.transmit : look.receive;
    context.fillRect(from, h - 2 * l.unit, to - from, 2 * l.unit);
    for (const x of [from, to - 2 * l.unit]) context.fillRect(x, h - 6 * l.unit, 2 * l.unit, 6 * l.unit);
  }

  /** The curve under the picture: a faint grid (a dotted line every 10 dB and every 500 Hz), the mean of the last seconds as a quiet shape, the floor as a level line over it, and the spectrum of the last second as
   * a bright line through the bins' centres, one CSS pixel thick. */
  private drawCurve(look: Look): void {
    const { context, l } = look;
    const { x, y, w, h } = l.curve;
    const yOf = (db: number): number =>
      y + Math.round((1 - (Math.max(CURVE_DB[0], Math.min(CURVE_DB[1], db)) - CURVE_DB[0]) / (CURVE_DB[1] - CURVE_DB[0])) * (h - l.unit));
    context.fillStyle = look.ground;
    context.fillRect(x, y - l.unit, w, h + l.unit);
    context.fillStyle = look.grid;
    context.fillRect(x, y - l.unit, w, l.unit);
    // the grid's dotted lines are one path of dashes, each line through the middle of its pixels
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
    // the shape and the line are drawn through the middle of the line's pixels, from the centre of one bin to the next
    const [average, now] = [curveMean(this.lines), curveNow(this.lines)].map((bytes) =>
      curvePoints(
        Array.from(bytes, (byte) => yOf(dbOfByte(byte)) + half),
        w,
      ),
    );
    context.globalAlpha = SHAPE_STRENGTH; // (before the first line the shape is the box's lowest line)
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
    if (this.lines.length === 0) return;
    context.strokeStyle = look.now;
    context.lineWidth = l.unit;
    context.lineJoin = "round";
    context.beginPath();
    now.forEach((point, i) => (i === 0 ? context.moveTo(point.x, point.y) : context.lineTo(point.x, point.y)));
    context.stroke();
  }
}
