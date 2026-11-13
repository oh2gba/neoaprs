// The HF radio's levels (lib/hflevel.ts): the zones of the receive level, the bar, and the numbers as text.
import { describe, expect, it } from "vitest";
import { GOOD_PERCENT, clips, dbText, gainText, levelPercent, levelZone } from "@/lib/hflevel";
import { LIMITS } from "@/protocol/lists";

describe("the receive level", () => {
  it("is low under the good range, good in it, high over it and clipping near full scale", () => {
    expect(LIMITS.scope.levelGoodDbfs).toEqual([-55, -25]);
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
