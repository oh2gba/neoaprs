// The scope's own logic (lib/scope.ts): the zones of the receive level, the bar, the text of the numbers, the ease of a picture toward the next, and the drawing of the spectrum on a canvas.
import { describe, expect, it, vi } from "vitest";
import {
  DRAW_RANGE_DB,
  GOOD_PERCENT,
  SCOPE_BINS,
  SIGNAL_BINS,
  clips,
  dbText,
  drawScope,
  ease,
  gainText,
  levelPercent,
  levelZone,
  scopeColours,
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

describe("ease", () => {
  it("takes a part of the way to the target at each step and comes to rest on it within half a dB", () => {
    let shown = [0, 40, 10];
    const target = [20, 0, 10];
    const first = ease(shown, target);
    expect(first.values[0]).toBeCloseTo(6);
    expect(first.values[1]).toBeCloseTo(28);
    expect(first.values[2]).toBe(10);
    expect(first.moving).toBe(true);
    shown = first.values;
    for (let i = 0; i < 60; i++) {
      const step = ease(shown, target);
      shown = step.values;
      if (!step.moving) break;
    }
    expect(shown).toEqual(target);
    expect(ease(shown, target).moving).toBe(false);
  });

  it("starts a bin that was not shown yet at its target", () => {
    expect(ease([], [5, 6])).toEqual({ values: [5, 6], moving: false });
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

describe("drawScope", () => {
  const colours = { line: "red", wash: "pink", band: "blue", grid: "grey" };

  it("sizes the canvas to the room it has, marks the signal band, rules every 10 dB and draws the bins as a filled line", () => {
    const { canvas, calls } = fakeCanvas(300, 72);
    drawScope(canvas, new Array<number>(SCOPE_BINS).fill(DRAW_RANGE_DB / 2), colours);
    expect(canvas.width).toBe(300);
    expect(canvas.height).toBe(72);
    const text = calls.join("\n");
    expect(text).toContain("clearRect(0,0,300,72)");
    expect(text).toContain(`fillRect(${(18 * 300) / 48},0,${(12 * 300) / 48},72)`);
    expect(calls.filter((c) => c.startsWith("stroke(")).length).toBe(3 + 1);
    expect(calls.filter((c) => c.startsWith("lineTo(")).length).toBe(3 + (SCOPE_BINS + 1) + (SCOPE_BINS - 1));
    expect(text).toContain("fillStyle=pink");
    expect(text).toContain("strokeStyle=red");
    expect(calls.filter((c) => c === "fill()")).toHaveLength(1);
  });

  it("cuts a signal off at the top of the picture and a negative bin at the floor", () => {
    const { canvas, calls } = fakeCanvas(96, 41);
    drawScope(canvas, [...new Array<number>(SCOPE_BINS - 2).fill(0), 500, -9], colours);
    const tops = calls.filter((c) => c.startsWith("lineTo(")).map((c) => Number(c.slice(7, -1).split(",")[1]));
    expect(Math.min(...tops)).toBe(2);
    expect(Math.max(...tops)).toBe(40);
  });

  it("does nothing on a canvas that has no context", () => {
    const canvas = document.createElement("canvas");
    vi.spyOn(canvas, "getContext").mockReturnValue(null);
    expect(() => drawScope(canvas, [1, 2, 3], colours)).not.toThrow();
  });
});

describe("scopeColours", () => {
  it("reads the page's tokens, the accent for what is received and the warning colour for our own signal", () => {
    const element = document.createElement("div");
    element.style.setProperty("--accent", "#111");
    element.style.setProperty("--warn", "#222");
    element.style.setProperty("--accent-soft-bg", "#333");
    element.style.setProperty("--warn-soft-bg", "#444");
    element.style.setProperty("--border", "#555");
    document.body.append(element);
    expect(scopeColours(element, false)).toEqual({ line: "#111", wash: "#333", band: "#333", grid: "#555" });
    expect(scopeColours(element, true)).toEqual({ line: "#222", wash: "#444", band: "#333", grid: "#555" });
    element.remove();
  });
});
