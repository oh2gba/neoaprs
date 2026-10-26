import { describe, expect, it } from "vitest";
import { placeNote } from "@/lib/infotip";

describe("placeNote: the note of an (i), wholly in the window", () => {
  const view = { width: 1440, height: 900 };
  const note = { width: 298, height: 200 };
  const at = (left: number, top: number, size = 20) => ({ left, top, right: left + size, bottom: top + size });

  it("is under the (i) with its right edge at the (i)'s, for an (i) at the right end of a row", () => {
    expect(placeNote(at(1400, 100), note, view)).toEqual({ left: 1420 - 298, top: 124, width: 298 });
  });

  it("is moved right to the margin where an (i) in the left column of the panel would leave it past the left edge of the window", () => {
    expect(placeNote(at(30, 100), note, view)).toEqual({ left: 8, top: 124, width: 298 });
  });

  it("is moved left where it would run past the right edge", () => {
    const wide = { width: 600, height: 100 };
    expect(placeNote(at(1430, 100), wide, view).left).toBe(1440 - 8 - 600);
  });

  it("opens above the (i) when it does not fit below and there is more room above", () => {
    expect(placeNote(at(700, 800), note, view)).toEqual({ left: 700 + 20 - 298, top: 800 - 4 - 200, width: 298 });
  });

  it("stays below when it does not fit anywhere better, and is not taller than the window's top", () => {
    expect(placeNote(at(700, 100), { width: 298, height: 880 }, view).top).toBe(124);
    expect(placeNote(at(700, 30), { width: 298, height: 880 }, { width: 1440, height: 400 }).top).toBeGreaterThanOrEqual(8);
  });

  it("is as wide as a phone allows: 360 px leaves 344 for a note that wants 298, and a wider note is cut to it, from the margin", () => {
    const phone = { width: 360, height: 640 };
    expect(placeNote(at(330, 200), note, phone)).toEqual({ left: 52, top: 224, width: 298 });
    expect(placeNote(at(330, 200), { width: 500, height: 100 }, phone)).toEqual({ left: 8, top: 224, width: 344 });
    expect(placeNote(at(10, 200), note, phone).left).toBe(8);
  });
});
