import { describe, expect, it } from "vitest";
import { covers, moveClearOf, type Box } from "@/lib/cardclear";

// a phone: a map 390 wide and 380 high, the card at its bottom with its top 130 px down (the most the card may be)
const phone: Box = { left: 0, top: 0, right: 390, bottom: 380 };
const phoneCard: Box = { left: 10, top: 130, right: 380, bottom: 370 };
// a desktop: a map 960 wide and 860 high, the card 340 wide at its bottom left corner
const desk: Box = { left: 0, top: 0, right: 960, bottom: 860 };
const deskCard: Box = { left: 10, top: 560, right: 350, bottom: 830 };

describe("covers", () => {
  it("is true for a marker under the card or its call, and false for one clear of it", () => {
    expect(covers(phoneCard, { x: 200, y: 250 })).toBe(true);
    expect(covers(phoneCard, { x: 200, y: 380 })).toBe(true); // the call under the marker is under the card
    expect(covers(phoneCard, { x: 200, y: 60 })).toBe(false);
    expect(covers(deskCard, { x: 600, y: 700 })).toBe(false);
    expect(covers(deskCard, { x: 200, y: 550 })).toBe(true); // the marker's edge is under the card
    expect(covers(deskCard, { x: 200, y: 530 })).toBe(false);
  });
});

describe("moveClearOf", () => {
  it("does nothing for a marker the card does not cover", () => {
    expect(moveClearOf(deskCard, { x: 600, y: 400 }, desk)).toBeNull();
  });

  it("moves a marker on a phone up, above the card, as there is no room beside it", () => {
    const move = moveClearOf(phoneCard, { x: 195, y: 190 }, phone);
    expect(move).toEqual({ x: 0, y: 130 - 40 - 190 });
    expect(190 + (move?.y ?? 0)).toBeLessThan(phoneCard.top);
  });

  it("moves a marker on a desktop the shorter way: up above the card when it is near its top, or to its right", () => {
    const up = moveClearOf(deskCard, { x: 200, y: 600 }, desk);
    expect(up).toEqual({ x: 0, y: 560 - 40 - 600 });
    const right = moveClearOf(deskCard, { x: 340, y: 700 }, desk);
    expect(right).toEqual({ x: 350 + 40 - 340, y: 0 });
  });

  it("does not put a marker under the zoom buttons: a card that reaches too high leaves the way beside it", () => {
    const tall: Box = { left: 10, top: 84, right: 350, bottom: 830 };
    const move = moveClearOf(tall, { x: 180, y: 400 }, desk);
    expect(move).toEqual({ x: 350 + 40 - 180, y: 0 });
  });

  it("gives up when there is no way left: a card over the whole map", () => {
    expect(moveClearOf({ left: 5, top: 84, right: 385, bottom: 370 }, { x: 195, y: 190 }, phone)).toBeNull();
  });

  it("does not move a marker to the right out of the map", () => {
    const wide: Box = { left: 10, top: 84, right: 700, bottom: 830 };
    expect(moveClearOf(wide, { x: 400, y: 400 }, { left: 0, top: 0, right: 760, bottom: 860 })).toBeNull();
  });
});
