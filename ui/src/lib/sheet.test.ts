import { describe, expect, it } from "vitest";
import { SWIPE_MIN, sheetMove } from "@/lib/sheet";

describe("sheetMove", () => {
  it("is a tap, which opens or folds, when the finger hardly moved", () => {
    expect(sheetMove(0, false)).toBe("toggle");
    expect(sheetMove(SWIPE_MIN - 1, true)).toBe("toggle");
    expect(sheetMove(-(SWIPE_MIN - 1), false)).toBe("toggle");
  });
  it("opens the sheet on a swipe up, whether it is open or not", () => {
    expect(sheetMove(-SWIPE_MIN, false)).toBe("expand");
    expect(sheetMove(-200, true)).toBe("expand");
  });
  it("folds an open sheet on a swipe down, and closes a folded one", () => {
    expect(sheetMove(SWIPE_MIN, true)).toBe("collapse");
    expect(sheetMove(SWIPE_MIN, false)).toBe("close");
    expect(sheetMove(300, false)).toBe("close");
  });
});
