import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// (the comments are taken out: a comment above a rule is not part of its selector)
const SHEET = readFileSync(resolve(__dirname, "../style.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

/** The declarations of the first rule of src/style.css whose selector is exactly `selector` (outside a media query), as written; "" when there is none. */
export function cssRule(selector: string): string {
  for (const match of SHEET.matchAll(/^([^{}@]+)\{([^{}]*)\}/gm)) {
    if ((match[1] ?? "").split(",").some((part) => part.trim() === selector)) return match[2] ?? "";
  }
  return "";
}

/** The declarations of the last rule inside the `@media` block whose condition is `query` (as written, e.g. "(max-width: 800px)") whose selector is exactly `selector`; "" when there is none. */
export function mediaRule(query: string, selector: string): string {
  const start = SHEET.indexOf(`@media ${query} {`);
  if (start < 0) return "";
  let depth = 0;
  let end = start;
  for (let i = SHEET.indexOf("{", start); i < SHEET.length; i++) {
    if (SHEET[i] === "{") depth++;
    if (SHEET[i] === "}" && --depth === 0) {
      end = i;
      break;
    }
  }
  let found = "";
  for (const match of SHEET.slice(start, end).matchAll(/([^{}@]+)\{([^{}]*)\}/g)) {
    if ((match[1] ?? "").split(",").some((part) => part.trim() === selector)) found = match[2] ?? "";
  }
  return found;
}
