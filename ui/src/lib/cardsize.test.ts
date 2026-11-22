import { describe, expect, it } from "vitest";
import { KEY_STEP, KEY_STEP_BIG } from "@/lib/cardmove";
import { clampSize, resizeByKey, resizeRect, sizeStep } from "@/lib/cardsize";

const least = { width: 300, height: 200 };
const room = { width: 1000, height: 700 };
const card = { x: 400, y: 300, width: 500, height: 300 };

describe("clampSize", () => {
  it("leaves a size within its limits as it is and rounds to whole pixels", () => {
    expect(clampSize({ width: 420.4, height: 250.6 }, least, room)).toEqual({ width: 420, height: 251 });
  });

  it("holds a size to the least and to the map", () => {
    expect(clampSize({ width: 10, height: 10 }, least, room)).toEqual(least);
    expect(clampSize({ width: 5000, height: 5000 }, least, room)).toEqual(room);
  });

  it("gives the map's room where the map is smaller than the least", () => {
    expect(clampSize({ width: 500, height: 500 }, least, { width: 250, height: 150 })).toEqual({
      width: 250,
      height: 150,
    });
  });
});

describe("resizeRect", () => {
  it("moves the right edge and keeps the left side", () => {
    expect(resizeRect(card, "e", 50, 99, least, room)).toEqual({ x: 400, y: 300, width: 550, height: 300 });
  });

  it("moves the left edge and keeps the right side", () => {
    expect(resizeRect(card, "w", -100, 0, least, room)).toEqual({ x: 300, y: 300, width: 600, height: 300 });
  });

  it("moves the top edge and keeps the bottom", () => {
    expect(resizeRect(card, "n", 0, -80, least, room)).toEqual({ x: 400, y: 220, width: 500, height: 380 });
  });

  it("moves two sides at a corner", () => {
    expect(resizeRect(card, "nw", -20, -30, least, room)).toEqual({ x: 380, y: 270, width: 520, height: 330 });
    expect(resizeRect(card, "se", 20, 30, least, room)).toEqual({ x: 400, y: 300, width: 520, height: 330 });
  });

  it("stops at the least size with the opposite side where it was", () => {
    expect(resizeRect(card, "w", 900, 0, least, room)).toEqual({ x: 600, y: 300, width: 300, height: 300 });
    expect(resizeRect(card, "s", 0, -900, least, room)).toEqual({ x: 400, y: 300, width: 500, height: 200 });
  });

  it("stops at the edge of the map", () => {
    expect(resizeRect(card, "e", 900, 0, least, room)).toEqual({ x: 400, y: 300, width: 600, height: 300 });
    expect(resizeRect(card, "w", -900, 0, least, room)).toEqual({ x: 0, y: 300, width: 900, height: 300 });
    expect(resizeRect(card, "n", 0, -900, least, room)).toEqual({ x: 400, y: 0, width: 500, height: 600 });
    expect(resizeRect(card, "s", 0, 900, least, room)).toEqual({ x: 400, y: 300, width: 500, height: 400 });
  });
});

describe("sizeStep", () => {
  it("makes the card larger with right and down and smaller with left and up, a bigger step with Shift", () => {
    expect(sizeStep("ArrowRight", false)).toEqual({ dx: KEY_STEP, dy: 0 });
    expect(sizeStep("ArrowUp", false)).toEqual({ dx: 0, dy: -KEY_STEP });
    expect(sizeStep("ArrowDown", true)).toEqual({ dx: 0, dy: KEY_STEP_BIG });
    expect(sizeStep("a", false)).toBeNull();
  });
});

describe("resizeByKey", () => {
  const map = { width: 1200, height: 800 };
  const corner = { x: 630, y: 290, width: 560, height: 480 }; // Stands at the map's bottom right

  it("makes a card at the map's bottom right larger to the left and up, its right and bottom sides staying", () => {
    expect(resizeByKey(corner, { dx: 24, dy: 0 }, least, map)).toEqual({ x: 606, y: 290, width: 584, height: 480 });
    expect(resizeByKey(corner, { dx: 0, dy: 96 }, least, map)).toEqual({ x: 630, y: 194, width: 560, height: 576 });
  });

  it("makes it smaller with left and up on the same side", () => {
    expect(resizeByKey(corner, { dx: -24, dy: 0 }, least, map)).toEqual({ x: 654, y: 290, width: 536, height: 480 });
  });

  it("makes a card at the map's top left larger to the right and down", () => {
    expect(resizeByKey({ x: 10, y: 10, width: 400, height: 300 }, { dx: 24, dy: 24 }, least, map)).toEqual({
      x: 10,
      y: 10,
      width: 424,
      height: 324,
    });
  });
});
