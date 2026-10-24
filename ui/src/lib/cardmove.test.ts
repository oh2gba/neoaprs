import { describe, expect, it } from "vitest";
import { KEY_STEP, KEY_STEP_BIG, clampPlace, keyStep } from "@/lib/cardmove";

// the row begins at (10, 84) of a map 1200 by 800: in the row's pixels the map is from (-10, -84) to (1190, 716)
const area = { left: -10, top: -84, right: 1190, bottom: 716 };
const size = { width: 340, height: 300 };

describe("clampPlace", () => {
  it("leaves a place that is inside the map as it is", () => {
    expect(clampPlace({ x: 100, y: 200 }, size, area)).toEqual({ x: 100, y: 200 });
  });

  it("brings a card back to each of the four edges, wholly inside", () => {
    expect(clampPlace({ x: -500, y: 100 }, size, area)).toEqual({ x: -10, y: 100 });
    expect(clampPlace({ x: 100, y: -500 }, size, area)).toEqual({ x: 100, y: -84 });
    expect(clampPlace({ x: 5000, y: 100 }, size, area)).toEqual({ x: 850, y: 100 });
    expect(clampPlace({ x: 100, y: 5000 }, size, area)).toEqual({ x: 100, y: 416 });
  });

  it("puts a card that is larger than the map at its top left corner, and rounds to whole pixels", () => {
    expect(clampPlace({ x: 300, y: 300 }, { width: 2000, height: 2000 }, area)).toEqual({ x: -10, y: -84 });
    expect(clampPlace({ x: 10.4, y: 20.6 }, size, area)).toEqual({ x: 10, y: 21 });
  });
});

describe("keyStep", () => {
  it("is a step for each arrow, a big one with Shift, and nothing for another key", () => {
    expect(keyStep("ArrowLeft", false)).toEqual({ x: -KEY_STEP, y: 0 });
    expect(keyStep("ArrowRight", false)).toEqual({ x: KEY_STEP, y: 0 });
    expect(keyStep("ArrowUp", true)).toEqual({ x: 0, y: -KEY_STEP_BIG });
    expect(keyStep("ArrowDown", true)).toEqual({ x: 0, y: KEY_STEP_BIG });
    expect(keyStep("a", false)).toBeNull();
  });
});
