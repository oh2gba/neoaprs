import { afterEach, describe, expect, it, vi } from "vitest";
import { reloadOnce } from "@/lib/reload";

afterEach(() => {
  sessionStorage.clear();
  vi.restoreAllMocks();
});

describe("reloadOnce", () => {
  it("loads the page again the first time and not the second", () => {
    const reload = vi.fn();
    vi.stubGlobal("location", { ...window.location, reload });
    expect(reloadOnce()).toBe(true);
    expect(reloadOnce()).toBe(false);
    expect(reload).toHaveBeenCalledOnce();
    vi.unstubAllGlobals();
  });
});
