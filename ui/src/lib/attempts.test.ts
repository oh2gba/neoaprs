import { describe, expect, it } from "vitest";
import { defaultAttempts, parseAttemptsText } from "@/lib/attempts";

describe("defaultAttempts", () => {
  it("is the setting, and 6 while it is not known or is no count", () => {
    expect(defaultAttempts({ "messages/attempts": "3" })).toBe(3);
    expect(defaultAttempts({ "messages/attempts": "10" })).toBe(10);
    expect(defaultAttempts(undefined)).toBe(6);
    expect(defaultAttempts({})).toBe(6);
    for (const bad of ["0", "11", "2.5", "many", ""]) expect(defaultAttempts({ "messages/attempts": bad })).toBe(6);
  });
});

describe("parseAttemptsText", () => {
  it("reads a whole number from 1 to 10, and an empty field as the default", () => {
    expect(parseAttemptsText(" 2 ")).toEqual({ count: 2 });
    expect(parseAttemptsText("10")).toEqual({ count: 10 });
    expect(parseAttemptsText("1")).toEqual({ count: 1 });
    expect(parseAttemptsText("")).toEqual({ count: null });
    expect(parseAttemptsText("  ")).toEqual({ count: null });
  });

  it("refuses anything else", () => {
    for (const bad of ["0", "11", "-1", "1.5", "two", "1e1"]) expect(parseAttemptsText(bad)).toBeNull();
  });
});
