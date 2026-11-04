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
  waterfallColours,
  type WaterfallColours,
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
  const colours: WaterfallColours = {
    scale: [
      [0, 8, 40],
      [8, 52, 190],
      [0, 170, 255],
      [255, 226, 0],
      [255, 40, 16],
    ],
    sent: [
      [40, 40, 40],
      [235, 235, 235],
    ],
    band: "pale",
    rule: "grey",
  };
  const cells = (calls: string[]) => calls.filter((c) => c.startsWith("fillRect(")).slice(1, -1);
  const row = (bins: number[], tx = false): Row => ({ bins, tx });
  const band = `fillRect(${Math.round((18 * 300) / 48)},0,${Math.round((30 * 300) / 48) - Math.round((18 * 300) / 48)},72)`;

  it("sizes the canvas to the room it has, fills it with the floor's colour, marks the signal band with a faint block between two dotted rules, and draws nothing else while there are no rows", () => {
    const { canvas, calls } = fakeCanvas(300, 72);
    drawWaterfall(canvas, [], colours);
    expect(canvas.width).toBe(300);
    expect(canvas.height).toBe(72);
    const text = calls.join("\n");
    expect(text).toContain("clearRect(0,0,300,72)");
    expect(calls.filter((c) => c.startsWith("fillRect("))).toEqual(["fillRect(0,0,300,72)", band]);
    expect(calls.filter((c) => c.startsWith("fillStyle="))).toEqual(["fillStyle=#000828", "fillStyle=pale"]);
    expect(calls.filter((c) => c.startsWith("stroke("))).toHaveLength(2);
    expect(text).toContain("strokeStyle=grey");
  });

  it("draws each row as a strip of cells, the newest at the top, received ones on the scale and our own transmission grey to white, the band over them", () => {
    const { canvas, calls } = fakeCanvas(96, 72);
    const strong = new Array<number>(SCOPE_BINS).fill(DRAW_RANGE_DB);
    drawWaterfall(canvas, [row(strong, true), row(strong)], colours);
    const drawn = cells(calls);
    expect(drawn).toHaveLength(2 * SCOPE_BINS);
    expect(drawn[0]).toBe(`fillRect(0,0,2,${ROW_PX})`);
    expect(drawn[SCOPE_BINS]).toBe(`fillRect(0,${ROW_PX},2,${ROW_PX})`);
    expect(drawn.at(-1)).toBe(`fillRect(94,${ROW_PX},2,${ROW_PX})`);
    const styles = calls.filter((c) => c.startsWith("fillStyle="));
    expect(styles[1]).toBe("fillStyle=#ebebeb");
    expect(styles[1 + SCOPE_BINS]).toBe("fillStyle=#ff2810");
    expect(styles.at(-1)).toBe("fillStyle=pale");
  });

  it("leaves a bin at the floor undrawn, so that the noise is the background, and draws only the rows that fit", () => {
    const { canvas, calls } = fakeCanvas(96, 5);
    const one = [...new Array<number>(SCOPE_BINS - 1).fill(0), DRAW_RANGE_DB / 2];
    drawWaterfall(canvas, [row(one), row(one), row(one), row(one)], colours);
    expect(cells(calls)).toEqual([`fillRect(94,0,2,${ROW_PX})`, `fillRect(94,${ROW_PX},2,${ROW_PX})`, `fillRect(94,${2 * ROW_PX},2,1)`]);
    expect(calls).toContain(`fillStyle=${heat(strength(DRAW_RANGE_DB / 2), colours.scale)}`);
  });

  it("does nothing on a canvas that has no context", () => {
    const canvas = document.createElement("canvas");
    vi.spyOn(canvas, "getContext").mockReturnValue(null);
    expect(() => drawWaterfall(canvas, [row([1, 2, 3])], colours)).not.toThrow();
  });
});

describe("the colour scale", () => {
  const scale = [
    [0, 8, 40],
    [8, 52, 190],
    [0, 170, 255],
    [255, 226, 0],
    [255, 40, 16],
  ] as const;

  it("puts its colours evenly from 0 to 1, mixes between two of them, and holds at the ends", () => {
    expect([0, 0.25, 0.5, 0.75, 1].map((s) => heat(s, scale))).toEqual(["#000828", "#0834be", "#00aaff", "#ffe200", "#ff2810"]);
    expect(heat(0.125, scale)).toBe("#041e73");
    expect(heat(-1, scale)).toBe("#000828");
    expect(heat(2, scale)).toBe("#ff2810");
    expect(heat(0.5, [[1, 2, 3]])).toBe("#010203");
    expect(heat(0.5, [])).toBe("#000000");
  });

  it("reads the page's --waterfall-* tokens: a rig's scale, and grey to white for our own transmission", () => {
    const element = document.createElement("div");
    [
      ["0", "#000828"],
      ["1", "#0834be"],
      ["2", "#00aaff"],
      ["3", "#ffe200"],
      ["4", "#ff2810"],
      ["sent-0", "#282828"],
      ["sent-1", "#ebebeb"],
    ].forEach(([name, value]) => element.style.setProperty(`--waterfall-${name}`, value ?? ""));
    element.style.setProperty("--waterfall-band", "pale");
    element.style.setProperty("--waterfall-rule", "grey");
    document.body.append(element);
    expect(waterfallColours(element)).toEqual({
      scale,
      sent: [
        [40, 40, 40],
        [235, 235, 235],
      ],
      band: "pale",
      rule: "grey",
    });
    element.remove();
  });
});
