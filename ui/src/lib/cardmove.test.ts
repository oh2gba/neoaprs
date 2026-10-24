import { describe, expect, it } from "vitest";
import { KEY_STEP, KEY_STEP_BIG, clampPlace, freeSlot, keyStep } from "@/lib/cardmove";

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

describe("freeSlot", () => {
  const row = { width: 1180, height: 686 };
  const at = (x: number, y = 386) => ({ x, y, width: 340, height: 300 });

  it("is the bottom left of the row when no card is there", () => {
    expect(freeSlot(size, [], row)).toEqual({ x: 0, y: 386 });
  });

  it("is the first slot from the left that no card overlaps: a slot that a card left is free again", () => {
    expect(freeSlot(size, [at(348), at(696)], row)).toEqual({ x: 0, y: 386 });
    expect(freeSlot(size, [at(0), at(696)], row)).toEqual({ x: 348, y: 386 });
  });

  it("goes to the right of a card that stands off the slots, and never on top of one", () => {
    expect(freeSlot(size, [at(20), at(348)], row)).toEqual({ x: 696, y: 386 });
    expect(freeSlot(size, [at(100, 50)], row)).toEqual({ x: 0, y: 386 });
    expect(freeSlot(size, [at(100, 100)], row)).toEqual({ x: 448, y: 386 });
  });

  it("uses the space beside a card that stands off the slots, in the row's narrower width, and above the cards when the bottom has none", () => {
    const narrow = { width: 1040, height: 686 };
    expect(freeSlot(size, [at(300, 100)], narrow)).toEqual({ x: 648, y: 386 });
    expect(freeSlot(size, [at(300, 100), at(648)], narrow)).toEqual({ x: 648, y: 78 });
  });

  it("goes to the row above when the bottom row has no room, and to the right of the rightmost card when the map is full", () => {
    expect(freeSlot(size, [at(0), at(348), at(696)], row)).toEqual({ x: 0, y: 78 });
    const full = [0, 348, 696].flatMap((x) => [at(x), at(x, 78)]);
    expect(freeSlot(size, full, row)).toEqual({ x: 1044, y: 386 });
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
