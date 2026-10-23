import { describe, expect, it } from "vitest";
import { ALL_SYMBOLS, filterSymbols, overlayOf, symbolName, tableWithOverlay, takesOverlay } from "@/lib/symbolpicker";
import { STATUS_CHOICES, statusShown, statusSource } from "@/lib/status";

describe("symbolName", () => {
  it("is the name in the table, and the alternate table's for an overlay table", () => {
    expect(symbolName("/", "-")).toBe("House");
    expect(symbolName("\\", "-")).toBe("House (HF)");
    expect(symbolName("S", "#")).toBe("Digipeater");
    expect(symbolName("5", ">")).toBe("Car");
  });
  it("numbers the circles of the primary table, and is empty for a symbol that is none", () => {
    expect(symbolName("/", "0")).toBe("Circle 0");
    expect(symbolName("/", "9")).toBe("Circle 9");
    expect(symbolName("/", '"')).toBe("");
    expect(symbolName("/", "|")).toBe("");
    expect(symbolName("/", "")).toBe("");
    expect(symbolName("/", " ")).toBe("");
  });
});

describe("overlays", () => {
  it("are for the alternate symbols made for them, and for a symbol that has one already", () => {
    expect(takesOverlay("\\", "#")).toBe(true);
    expect(takesOverlay("\\", ">")).toBe(true);
    expect(takesOverlay("\\", "-")).toBe(false);
    expect(takesOverlay("/", "#")).toBe(false);
    expect(takesOverlay("S", "-")).toBe(true);
  });
  it("are a capital or a digit, and anything else is none", () => {
    expect(["S", "7", "\\", "/"].map(overlayOf)).toEqual(["S", "7", "", ""]);
    expect(["s", " 3 ", "", "-", "ab"].map(tableWithOverlay)).toEqual(["S", "3", "\\", "\\", "A"]);
  });
});

describe("filterSymbols", () => {
  const names = (query: string) => filterSymbols(ALL_SYMBOLS, query).map((s) => s.name);
  it("is everything for an empty query", () => {
    expect(filterSymbols(ALL_SYMBOLS, "")).toHaveLength(ALL_SYMBOLS.length);
  });
  it("needs every word, in any case, anywhere in the name", () => {
    expect(names("HOUSE")).toEqual(expect.arrayContaining(["House", "House (HF)"]));
    expect(names("weather station")).toEqual(expect.arrayContaining(["Weather station", "Weather station (green)"]));
    expect(names("station weather")).toEqual(names("weather station"));
    expect(names("car zzz")).toEqual([]);
  });
  it("knows the words people use", () => {
    expect(names("wx")).toContain("Weather station");
    expect(names("igate")).toContain("Gateway");
    expect(names("plane")).toEqual(expect.arrayContaining(["Large aircraft", "Small aircraft"]));
    expect(names("digi")).toEqual(["Digipeater", "Digipeater"]);
  });
  it("finds a symbol written as table and code", () => {
    expect(filterSymbols(ALL_SYMBOLS, "/-").map((s) => s.name)).toContain("House");
  });
});

describe("the status choices", () => {
  it("are off, a text of my own and the radio", () => {
    expect(STATUS_CHOICES.map((c) => c.value)).toEqual(["off", "text", "rig"]);
  });
  it("follow the settings while the choice is empty, as the daemon does", () => {
    expect(statusSource({})).toBe("off");
    expect(statusSource({ "station/status": " QRV " })).toBe("text");
    expect(statusSource({ "station/status": "QRV", "status/rigctld": "127.0.0.1:4532" })).toBe("rig");
    expect(statusSource({ "status/source": "", "status/rigctld": "127.0.0.1:4532" })).toBe("rig");
  });
  it("are what was chosen, whatever else is set", () => {
    expect(statusSource({ "status/source": "text", "status/rigctld": "127.0.0.1:4532" })).toBe("text");
    expect(statusSource({ "status/source": "OFF", "station/status": "QRV" })).toBe("off");
    expect(statusSource({ "status/source": "rig" })).toBe("rig");
    expect(statusSource({ "status/source": "nonsense", "station/status": "QRV" })).toBe("text");
  });
  it("show the fields they need", () => {
    const keys = ["status/source", "station/status", "status/rigctld", "status/template", "status/interval_min"];
    expect(keys.filter((k) => statusShown(k, "off"))).toEqual(["status/source"]);
    expect(keys.filter((k) => statusShown(k, "text"))).toEqual(["status/source", "station/status", "status/interval_min"]);
    expect(keys.filter((k) => statusShown(k, "rig"))).toEqual(["status/source", "status/rigctld", "status/template", "status/interval_min"]);
  });
});
