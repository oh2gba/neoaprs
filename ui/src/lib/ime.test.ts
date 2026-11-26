import { describe, expect, it } from "vitest";
import { confirms } from "@/lib/ime";

const key = (init: KeyboardEventInit): KeyboardEvent => new KeyboardEvent("keydown", init);

describe("the Enter that confirms a field", () => {
  it("is an Enter outside an IME composition", () => {
    expect(confirms(key({ key: "Enter" }))).toBe(true);
    expect(confirms(key({ key: "Enter", isComposing: true }))).toBe(false);
    expect(confirms(key({ key: "Enter", keyCode: 229 }))).toBe(false);
  });
});
