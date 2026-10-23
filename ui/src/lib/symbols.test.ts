import { describe, expect, it } from "vitest";
import { setLocale } from "@/i18n";
import { SPRITE_COLUMNS, SPRITE_PX, cellOf, layerStyle, symbolLayers, symbolText } from "@/lib/symbols";
import { SYMBOL_NAMES } from "@/protocol/lists";

describe("cellOf", () => {
  it("lays the codes ! to ~ out 16 to a row from the top left", () => {
    expect(cellOf("!")).toEqual({ column: 0, row: 0 });
    expect(cellOf("-")).toEqual({ column: 12, row: 0 }); // the house
    expect(cellOf("0")).toEqual({ column: 15, row: 0 });
    expect(cellOf("1")).toEqual({ column: 0, row: 1 });
    expect(cellOf(">")).toEqual({ column: 13, row: 1 }); // the car
    expect(cellOf("A")).toEqual({ column: 0, row: 2 });
    expect(cellOf("~")).toEqual({ column: 13, row: 5 });
  });
  it("has no cell for a character outside the tables", () => {
    expect(cellOf(" ")).toBeNull();
    expect(cellOf("")).toBeNull();
    expect(cellOf("ab")).toBeNull();
    expect(cellOf("\x7f")).toBeNull();
  });
  it("gives every code a different cell inside the sheet", () => {
    const seen = new Set<string>();
    for (let code = 0x21; code <= 0x7e; code++) {
      const cell = cellOf(String.fromCharCode(code));
      expect(cell).not.toBeNull();
      expect(cell?.column).toBeLessThan(SPRITE_COLUMNS);
      seen.add(`${cell?.column},${cell?.row}`);
    }
    expect(seen.size).toBe(94);
  });
});

describe("symbolLayers", () => {
  it("is the primary sheet for the table / and the alternate for \\", () => {
    expect(symbolLayers("/", ">")).toEqual([{ sheet: "primary", column: 13, row: 1 }]);
    expect(symbolLayers("\\", "#")).toEqual([{ sheet: "alternate", column: 2, row: 0 }]);
  });
  it("puts the overlay character over the alternate symbol for an overlay table", () => {
    expect(symbolLayers("N", "#")).toEqual([
      { sheet: "alternate", column: 2, row: 0 },
      { sheet: "overlay", column: 13, row: 2 },
    ]);
    expect(symbolLayers("5", "#")[1]).toEqual({ sheet: "overlay", column: 4, row: 1 });
  });
  it("is empty for a symbol that is none", () => {
    expect(symbolLayers("", "")).toEqual([]);
    expect(symbolLayers("/", "")).toEqual([]);
    expect(symbolLayers("?", ">")).toEqual([]);
  });
});

describe("layerStyle", () => {
  it("shows the sheet as the background, moved to the cell", () => {
    const style = layerStyle({ sheet: "primary", column: 13, row: 1 }, 26);
    expect(style.backgroundImage).toBe("url(symbols/primary.png)");
    expect(style.backgroundSize).toBe("416px 156px");
    expect(style.backgroundPosition).toBe("-338px -26px");
  });
  it("knows the size of a cell of the sheets in the build", () => {
    expect(SPRITE_PX).toBe(48);
  });
});

describe("symbolText", () => {
  it("names the symbol of a table and a code, an overlay table being the alternate one", () => {
    expect([symbolText("/", ">"), symbolText("\\", ">"), symbolText("S", "#"), symbolText("a", "#"), symbolText("/", "_")]).toEqual([
      "Car",
      "Car",
      "Digipeater",
      "Digipeater",
      "Weather station",
    ]);
  });
  it("has the name of every code of the daemon's lists", () => {
    for (const [table, names] of [
      ["/", SYMBOL_NAMES.primary],
      ["\\", SYMBOL_NAMES.alternate],
    ] as const)
      names.forEach((name, index) => expect(symbolText(table, String.fromCharCode(33 + index))).toBe(name));
  });
  it("says unknown for a symbol that is none", () => {
    expect([symbolText("", ""), symbolText("/", ""), symbolText("?", ">"), symbolText("/", " "), symbolText("/", "\u007f")]).toEqual(Array(5).fill("unknown"));
  });
  it("is in the language of the page", () => {
    setLocale("en-XA");
    expect(symbolText("/", ">")).toMatch(/^\[!! /);
  });
});
