// The satellite card's table of where to tune stands in the column of the card's text: its sides
// are the card's fields' own.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const sheet = (file: string): string => readFileSync(resolve(__dirname, file), "utf8");
const rule = (css: string, selector: string): string => {
  const at = css.indexOf(`${selector} {`);
  return at < 0 ? "" : css.slice(at, css.indexOf("}", at));
};

describe("the satellite card's table to tune", () => {
  it("has the sides of the card's fields, so that it lines up with the text above it", () => {
    expect(rule(sheet("card.css"), ".card-fields")).toContain("padding: 6px var(--card-side) 8px");
    expect(rule(sheet("map.css"), ".satcard-tune")).toContain("margin: 0 var(--card-side) 8px");
    expect(rule(sheet("card.css"), ".card")).toContain("--card-side: 10px");
  });
});
