import { afterEach, describe, expect, it, vi } from "vitest";
import { readStored, readStoredNumber, removeStored, writeStored } from "@/lib/storage";
import { readView, writeView } from "@/lib/mapview";

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("storage", () => {
  it("keeps and returns a text", () => {
    writeStored("a", "b");
    expect(readStored("a")).toBe("b");
    expect(readStored("missing")).toBeNull();
  });
  it("removes a text", () => {
    writeStored("a", "b");
    removeStored("a");
    expect(readStored("a")).toBeNull();
  });
  it("reads a number inside its limits, else the fallback", () => {
    writeStored("n", "300");
    expect(readStoredNumber("n", 5, 0, 500)).toBe(300);
    expect(readStoredNumber("n", 5, 0, 100)).toBe(5);
    writeStored("n", "junk");
    expect(readStoredNumber("n", 5, 0, 100)).toBe(5);
    expect(readStoredNumber("absent", 7, 0, 100)).toBe(7);
  });
  it("works without storage", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readStored("a")).toBeNull();
    expect(() => writeStored("a", "b")).not.toThrow();
  });
});

describe("the map's view", () => {
  it("is remembered", () => {
    writeView({ lat: 60.123456789, lon: 24.9, zoom: 10.123456 });
    expect(readView()).toEqual({ lat: 60.12346, lon: 24.9, zoom: 10.12 });
  });
  it("is none for garbage", () => {
    expect(readView()).toBeNull();
    writeStored("mapview", "{not json");
    expect(readView()).toBeNull();
    writeStored("mapview", JSON.stringify({ lat: 120, lon: 0, zoom: 3 }));
    expect(readView()).toBeNull();
    writeStored("mapview", JSON.stringify({ lat: 1, lon: 2 }));
    expect(readView()).toBeNull();
    writeStored("mapview", JSON.stringify({ lat: 1, lon: 2, zoom: 99 }));
    expect(readView()).toBeNull();
  });
});
