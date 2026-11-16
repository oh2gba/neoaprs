import { describe, expect, it } from "vitest";
import { GOOD_PERCENT, levelPercent, levelText, levelZone } from "@/lib/soundcardlevel";
import { LIMITS } from "@/protocol/lists";

describe("the receive level of a Sound card radio", () => {
  it("is red where Direwolf itself says too high, good round its 50, low under it (between packets, or with the radio off), and between good and red neither", () => {
    expect(LIMITS.soundCard).toMatchObject({ levelMax: 200, levelLow: 5, levelHigh: 110, levelGood: [30, 70] });
    expect([0, 4, 5, 29, 30, 50, 70, 71, 110, 111, 199].map(levelZone)).toEqual([
      "low",
      "low",
      "low",
      "low",
      "good",
      "good",
      "good",
      "high",
      "high",
      "clip",
      "clip",
    ]);
  });

  it("is on a bar from 0 to 200, its good band at 30 to 70, and a dash before a packet is heard", () => {
    expect([levelPercent(0), levelPercent(50), levelPercent(200), levelPercent(250)]).toEqual([0, 25, 100, 100]);
    expect(GOOD_PERCENT).toEqual([15, 35]);
    expect([levelText(null), levelText(48)]).toEqual(["–", "48"]);
  });
});
