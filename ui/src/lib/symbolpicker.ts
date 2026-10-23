// What the symbol picker lists and how it finds a symbol: every symbol of the primary and of the alternate table with its name (the daemon's own list, SYMBOL_NAMES of the generated lists), without the codes
// the specification keeps reserved, searched by words ("house", "car", "digi", "wx"). A symbol is written the way the settings write it, as two characters: the table (`/` primary, `\` alternate, or a digit or
// a capital letter, which is the alternate table with that character drawn over the symbol) and the code (`-` is a house).
import { SYMBOL_NAMES } from "@/protocol/lists";

export interface PickSymbol {
  /** `/` or `\`: the table the symbol is in (an overlay is a character that goes over an alternate symbol). */
  table: string;
  code: string;
  name: string;
}

const FIRST_CODE = 33;
const NOT_LISTED = ["reserved", "TNC stream switch"];
/** The alternate symbols that are made to carry a letter or a digit over them (a digipeater of a network, a car of a kind: `S#`, `E>`). */
const OVERLAY_CODES = "#&0>A^_acisuv";
const OVERLAY_CHARS = /^[0-9A-Z]$/;
/** Words that people look for and the names do not use: what they stand for. */
const SYNONYMS: Record<string, string> = {
  wx: "weather",
  igate: "gateway",
  plane: "aircraft",
  airplane: "aircraft",
  bike: "bicycle",
  ship: "boat",
  cottage: "house",
  home: "house",
};

function nameOf(table: string, index: number): string {
  const name = (table === "/" ? SYMBOL_NAMES.primary : SYMBOL_NAMES.alternate)[index] ?? "";
  // the ten numbered circles of the primary table are all called "Circle" by the list
  return table === "/" && name === "Circle" ? `Circle ${String.fromCharCode(index + FIRST_CODE)}` : name;
}

/** Every symbol that can be chosen: the primary table, then the alternate one. */
export const ALL_SYMBOLS: readonly PickSymbol[] = ["/", "\\"].flatMap((table) =>
  (table === "/" ? SYMBOL_NAMES.primary : SYMBOL_NAMES.alternate)
    .map((_, index) => ({ table, code: String.fromCharCode(index + FIRST_CODE), name: nameOf(table, index) }))
    .filter((s) => !NOT_LISTED.includes(s.name)),
);

/** The name of the symbol of this table and code, "" for one that is none. An overlay table is the alternate table. */
export function symbolName(table: string, code: string): string {
  const index = code.length === 1 ? code.charCodeAt(0) - FIRST_CODE : -1;
  const name = index >= 0 ? nameOf(table === "/" ? "/" : "\\", index) : "";
  return NOT_LISTED.includes(name) ? "" : name;
}

/** Whether a letter or a digit can go over the symbol: the symbols made for it, and any that has one already. */
export function takesOverlay(table: string, code: string): boolean {
  return table !== "/" && (OVERLAY_CHARS.test(table) || OVERLAY_CODES.includes(code));
}

/** The overlay character of a table ("" for the primary and the plain alternate table). */
export function overlayOf(table: string): string {
  return OVERLAY_CHARS.test(table) ? table : "";
}

/** The table for an alternate symbol with this overlay typed: the character in capitals when it is a digit or a letter, else `\` (none). */
export function tableWithOverlay(typed: string): string {
  const char = typed.trim().toUpperCase().slice(0, 1);
  return OVERLAY_CHARS.test(char) ? char : "\\";
}

/** The symbols whose name has every word of the query (a synonym counts for the word it stands for), or that are written as the query (`/-`); all of them for an empty query. */
export function filterSymbols(symbols: readonly PickSymbol[], query: string): PickSymbol[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return [...symbols];
  return symbols.filter(
    (s) => `${s.table}${s.code}` === query.trim() || words.every((w) => s.name.toLowerCase().includes(SYNONYMS[w] ?? w) || s.name.toLowerCase().includes(w)),
  );
}
