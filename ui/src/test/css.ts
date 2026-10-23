import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const SHEET = readFileSync(resolve(__dirname, "../style.css"), "utf8");

/** The declarations of the first rule of src/style.css whose selector is exactly `selector` (outside a media query), as written; "" when there is none. */
export function cssRule(selector: string): string {
  for (const match of SHEET.matchAll(/^([^{}@]+)\{([^{}]*)\}/gm)) {
    if ((match[1] ?? "").split(",").some((part) => part.trim() === selector)) return match[2] ?? "";
  }
  return "";
}
