import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// (the comments are taken out: a comment above a rule is not part of its selector.) The page's two style sheets, as one: style.css, then responsive.css
const SHEET = ["../style.css", "../responsive.css"]
  .map((file) => readFileSync(resolve(__dirname, file), "utf8"))
  .join("\n")
  .replace(/\/\*[\s\S]*?\*\//g, "");

/** The declarations of the rules of the style sheets whose selector is exactly `selector` (outside a media query), as written, one after the other; "" when there is none. */
export function cssRule(selector: string): string {
  let found = "";
  for (const match of SHEET.matchAll(/^([^{}@]+)\{([^{}]*)\}/gm)) {
    if ((match[1] ?? "").split(",").some((part) => part.trim() === selector)) found += match[2] ?? "";
  }
  return found;
}

/** The declarations of the rules inside the `@media` block whose condition is `query` (as written, e.g. "(pointer: coarse)") whose selector is exactly `selector`, one after the other; "" when there is none. */
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
    if ((match[1] ?? "").split(",").some((part) => part.trim() === selector)) found += match[2] ?? "";
  }
  return found;
}
