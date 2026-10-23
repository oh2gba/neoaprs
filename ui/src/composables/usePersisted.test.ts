import { nextTick } from "vue";
import { beforeEach, describe, expect, it } from "vitest";
import { usePersisted, usePersistedFlag, usePersistedNumber } from "@/composables/usePersisted";

beforeEach(() => localStorage.clear());

describe("usePersisted", () => {
  it("starts from what was stored when it is one of the words, and stores a change", async () => {
    localStorage.setItem("NeoAPRS.tab", "packets");
    const tab = usePersisted("tab", "stations", ["stations", "packets"] as const);
    expect(tab.value).toBe("packets");
    tab.value = "stations";
    await nextTick();
    expect(localStorage.getItem("NeoAPRS.tab")).toBe("stations");
    localStorage.setItem("NeoAPRS.tab", "nonsense");
    expect(usePersisted("tab", "stations", ["stations", "packets"] as const).value).toBe("stations");
  });

  it("keeps a number inside its range", () => {
    localStorage.setItem("NeoAPRS.width", "99999");
    expect(usePersistedNumber("width", 400, 280, 20000).value).toBe(400);
    localStorage.setItem("NeoAPRS.width", "500");
    expect(usePersistedNumber("width", 400, 280, 20000).value).toBe(500);
  });
});

describe("usePersistedFlag", () => {
  it("is yes or no, stored as its two words, and the fallback for anything else", async () => {
    const flag = usePersistedFlag("panel", ["collapsed", "open"], false);
    expect(flag.value).toBe(false);
    flag.value = true;
    await nextTick();
    expect(localStorage.getItem("NeoAPRS.panel")).toBe("collapsed");
    flag.value = false;
    await nextTick();
    expect(localStorage.getItem("NeoAPRS.panel")).toBe("open");
    localStorage.setItem("NeoAPRS.panel", "collapsed");
    expect(usePersistedFlag("panel", ["collapsed", "open"], false).value).toBe(true);
    localStorage.setItem("NeoAPRS.panel", "sideways");
    expect(usePersistedFlag("panel", ["collapsed", "open"], true).value).toBe(true);
  });
});
