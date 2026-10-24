import { afterEach, describe, expect, it, vi } from "vitest";
import { loadPinned, savePinned } from "@/lib/pinned";

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("pinned cards in the browser's storage", () => {
  it("remembers the calls in order, each with its place or null", () => {
    savePinned(["OH2ZWB", "OH2ZWA"], { OH2ZWA: { x: 12, y: 340 }, OH2ZWC: { x: 1, y: 1 } });
    expect(Object.entries(loadPinned())).toEqual([
      ["OH2ZWB", null],
      ["OH2ZWA", { x: 12, y: 340 }],
    ]);
  });

  it("stores nothing when nothing is pinned, and removes what was stored", () => {
    savePinned(["OH2ZWA"], {});
    expect(localStorage.getItem("NeoAPRS.pinnedcards")).not.toBeNull();
    savePinned([], { OH2ZWA: { x: 1, y: 2 } });
    expect(localStorage.getItem("NeoAPRS.pinnedcards")).toBeNull();
    expect(loadPinned()).toEqual({});
  });

  it("leaves out what is not a call with a place or null, and reads nothing from text that is not an object", () => {
    localStorage.setItem("NeoAPRS.pinnedcards", JSON.stringify({ A: { x: 1, y: 2 }, B: null, C: { x: "1", y: 2 }, D: 5, E: { x: null, y: 1 }, F: "x" }));
    expect(loadPinned()).toEqual({ A: { x: 1, y: 2 }, B: null });
    for (const text of ["not json", "[1,2]", "7", "null", ""]) {
      localStorage.setItem("NeoAPRS.pinnedcards", text);
      expect(loadPinned(), text).toEqual({});
    }
  });

  it("works without storage: nothing is read and nothing is thrown", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(loadPinned()).toEqual({});
    expect(() => savePinned(["A"], {})).not.toThrow();
    expect(() => savePinned([], {})).not.toThrow();
  });
});
