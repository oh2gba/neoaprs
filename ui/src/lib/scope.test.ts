// The scope's own logic (lib/scope.ts): the zones of the receive level, the bar, the text of the numbers, the rows of the waterfall, and the drawing of the waterfall on a canvas.
import { describe, expect, it, vi } from "vitest";
import {
  DRAW_RANGE_DB,
  GOOD_PERCENT,
  KEPT_ROWS,
  ROW_PX,
  SCOPE_BINS,
  SIGNAL_BINS,
  addRow,
  clips,
  dbText,
  drawWaterfall,
  gainText,
  levelPercent,
  levelZone,
  heat,
  sentHeat,
  HEAT,
  strength,
  type Row,
} from "@/lib/scope";
import { LIMITS } from "@/protocol/lists";

describe("the numbers of the scope", () => {
  it("come from the daemon: 48 bins of 50 Hz over 300 to 2700 Hz, and the frame's signal band is bins 18 to 30", () => {
    expect(SCOPE_BINS).toBe(48);
    expect(SIGNAL_BINS).toEqual([18, 30]);
    expect(LIMITS.scope.levelGoodDbfs).toEqual([-55, -25]);
  });
});

describe("the receive level", () => {
  it("is low under the good range, good in it, high over it and clipping near full scale", () => {
    expect([-90, -60, -55.1].map(levelZone)).toEqual(["low", "low", "low"]);
    expect([-55, -40, -25].map(levelZone)).toEqual(["good", "good", "good"]);
    expect([-24, -11].map(levelZone)).toEqual(["high", "high"]);
    expect([-10, -3, 0].map(levelZone)).toEqual(["clip", "clip", "clip"]);
  });

  it("is a place on the bar from the silence of -90 dBFS to full scale, and the good range is the part of it between its two ends", () => {
    expect([-90, -45, 0].map(levelPercent)).toEqual([0, 50, 100]);
    expect([-200, 12].map(levelPercent)).toEqual([0, 100]);
    expect(GOOD_PERCENT[0]).toBeCloseTo(((90 - 55) / 90) * 100);
    expect(GOOD_PERCENT[1]).toBeCloseTo(((90 - 25) / 90) * 100);
  });
});

describe("the numbers as text", () => {
  it("are whole dB with a plus on a raise, and a dash for a peak not yet known", () => {
    expect([-20, -1, 0, 1, 20].map(gainText)).toEqual(["-20", "-1", "0", "+1", "+20"]);
    expect([-38, 0, null].map(dbText)).toEqual(["-38", "0", "–"]);
  });

  it("call a peak at 0 dBFS or over a clip and nothing under it, nor an unknown one", () => {
    expect([null, -6, -0.5].map(clips)).toEqual([false, false, false]);
    expect([0, 1, 13].map(clips)).toEqual([true, true, true]);
  });
});

describe("the rows of the waterfall", () => {
  const row = (db: number, tx = false): Row => ({ bins: new Array<number>(SCOPE_BINS).fill(db), tx });

  it("put the newest picture on top and let the oldest go past the ones kept", () => {
    let rows: Row[] = [];
    for (let i = 0; i < KEPT_ROWS + 5; i++) rows = addRow(rows, row(i));
    expect(rows).toHaveLength(KEPT_ROWS);
    expect(rows[0].bins[0]).toBe(KEPT_ROWS + 4);
    expect(rows.at(-1)?.bins[0]).toBe(5);
    expect(addRow([row(1), row(2)], row(3), 2).map((r) => r.bins[0])).toEqual([3, 1]);
  });

  it("are as strong as the bin over the floor: nothing at the floor and under it, full at the top of the range and over it, more than in proportion between", () => {
    expect([-5, 0].map(strength)).toEqual([0, 0]);
    expect([DRAW_RANGE_DB, DRAW_RANGE_DB + 20].map(strength)).toEqual([1, 1]);
    expect(strength(DRAW_RANGE_DB / 2)).toBeGreaterThan(0.5);
    expect(strength(5)).toBeLessThan(strength(10));
  });
});

function fakeCanvas(width = 300, height = 72) {
  const calls: string[] = [];
  const context = new Proxy(
    {},
    {
      get: (_target, name: string) => (name === "canvas" ? undefined : (...args: unknown[]) => calls.push(`${name}(${args.join(",")})`)),
      set: (_target, name: string, value: unknown) => {
        calls.push(`${name}=${String(value)}`);
        return true;
      },
    },
  );
  const canvas = document.createElement("canvas");
  Object.defineProperty(canvas, "clientWidth", { value: width });
  Object.defineProperty(canvas, "clientHeight", { value: height });
  vi.spyOn(canvas, "getContext").mockReturnValue(context as unknown as CanvasRenderingContext2D);
  return { canvas, calls };
}

describe("drawWaterfall", () => {
  const cells = (calls: string[]) => calls.filter((c) => c.startsWith("fillRect(")).slice(1, -1);
  const row = (bins: number[], tx = false): Row => ({ bins, tx });
  const band = `fillRect(${Math.round((18 * 300) / 48)},0,${Math.round((30 * 300) / 48) - Math.round((18 * 300) / 48)},72)`;

  it("sizes the canvas to the room it has, fills it with the floor's navy, marks the signal band with a faint light block between two dotted rules, and draws nothing else while there are no rows", () => {
    const { canvas, calls } = fakeCanvas(300, 72);
    drawWaterfall(canvas, []);
    expect(canvas.width).toBe(300);
    expect(canvas.height).toBe(72);
    const text = calls.join("\n");
    expect(text).toContain("clearRect(0,0,300,72)");
    expect(calls.filter((c) => c.startsWith("fillRect("))).toEqual(["fillRect(0,0,300,72)", band]);
    expect(calls.filter((c) => c.startsWith("fillStyle="))).toEqual([`fillStyle=${heat(0)}`, "fillStyle=rgba(255, 255, 255, 0.07)"]);
    expect(calls.filter((c) => c.startsWith("stroke("))).toHaveLength(2);
    expect(text).toContain("strokeStyle=rgba(255, 255, 255, 0.45)");
  });

  it("draws each row as a strip of cells, the newest at the top, received ones on the colour scale and our own transmission grey to white, the band over them", () => {
    const { canvas, calls } = fakeCanvas(96, 72);
    const strong = new Array<number>(SCOPE_BINS).fill(DRAW_RANGE_DB);
    drawWaterfall(canvas, [row(strong, true), row(strong)]);
    const drawn = cells(calls);
    expect(drawn).toHaveLength(2 * SCOPE_BINS);
    expect(drawn[0]).toBe(`fillRect(0,0,2,${ROW_PX})`);
    expect(drawn[SCOPE_BINS]).toBe(`fillRect(0,${ROW_PX},2,${ROW_PX})`);
    expect(drawn.at(-1)).toBe(`fillRect(94,${ROW_PX},2,${ROW_PX})`);
    const styles = calls.filter((c) => c.startsWith("fillStyle="));
    expect(styles[1]).toBe(`fillStyle=${sentHeat(1)}`);
    expect(styles[1 + SCOPE_BINS]).toBe(`fillStyle=${heat(1)}`);
    expect(styles.at(-1)).toBe("fillStyle=rgba(255, 255, 255, 0.07)");
  });

  it("leaves a bin at the floor undrawn, so that the noise is the background, and draws only the rows that fit", () => {
    const { canvas, calls } = fakeCanvas(96, 5);
    const one = [...new Array<number>(SCOPE_BINS - 1).fill(0), DRAW_RANGE_DB / 2];
    drawWaterfall(canvas, [row(one), row(one), row(one), row(one)]);
    expect(cells(calls)).toEqual([`fillRect(94,0,2,${ROW_PX})`, `fillRect(94,${ROW_PX},2,${ROW_PX})`, `fillRect(94,${2 * ROW_PX},2,1)`]);
    expect(calls).toContain(`fillStyle=${heat(strength(DRAW_RANGE_DB / 2))}`);
  });

  it("does nothing on a canvas that has no context", () => {
    const canvas = document.createElement("canvas");
    vi.spyOn(canvas, "getContext").mockReturnValue(null);
    expect(() => drawWaterfall(canvas, [row([1, 2, 3])])).not.toThrow();
  });
});

describe("the colour scale", () => {
  it("runs as a rig's waterfall, navy at the floor through blue, cyan and yellow to red, and holds at the ends", () => {
    expect(heat(0)).toBe("rgb(0, 8, 40)");
    expect(heat(0.25)).toBe("rgb(8, 52, 190)");
    expect(heat(0.5)).toBe("rgb(0, 170, 255)");
    expect(heat(0.75)).toBe("rgb(255, 226, 0)");
    expect(heat(1)).toBe("rgb(255, 40, 16)");
    expect(heat(0.125)).toBe("rgb(4, 30, 115)");
    expect(heat(-1)).toBe(heat(0));
    expect(heat(2)).toBe(heat(1));
    expect(HEAT.map(([at]) => at)).toEqual([0, 0.25, 0.5, 0.75, 1]);
  });

  it("draws our own transmission grey to white, apart from the scale", () => {
    expect(sentHeat(0)).toBe("rgb(40, 40, 40)");
    expect(sentHeat(1)).toBe("rgb(235, 235, 235)");
  });
});
