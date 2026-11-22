// What the symbol picker lists and how it finds a symbol: every symbol of the primary and alternate
// table with its name (the daemon's SYMBOL_NAMES of the generated lists), without the codes the
// specification keeps reserved, searched by words ("house", "car", "digi", "wx"). A symbol is
// written as the settings write it, as two characters: the table (`/` primary, `\` alternate, or
// a digit or capital letter, which is the alternate table with that character drawn over the
// symbol) and the code (`-` is a house).
import { t } from "@/i18n";
import { symbolText } from "@/lib/symbols";
import { SYMBOL_NAMES } from "@/protocol/lists";

export interface PickSymbol {
  /** `/` or `\`: the table the symbol is in (an overlay is a character drawn over an alternate
   * symbol). */
  table: string;
  code: string;
  name: string;
}

const FIRST_CODE = 33;
const NOT_LISTED = ["reserved", "TNC stream switch"];
/** The alternate symbols made to carry a letter or digit over them (a network's digipeater, a kind
 * of car: `S#`, `E>`). */
const OVERLAY_CODES = "#&0>A^_acisuv";
const OVERLAY_CHARS = /^[0-9A-Z]$/;
/** Words that people look for and the names do not use, and what they stand for. */
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

function tableList(table: string): readonly string[] {
  return table === "/" ? SYMBOL_NAMES.primary : SYMBOL_NAMES.alternate;
}

/** The name of the symbol at an index of a table, in the page's language. */
function nameOf(table: string, index: number): string {
  const code = String.fromCharCode(index + FIRST_CODE);
  const name = symbolText(table, code);
  // The list calls the ten numbered circles of the primary table all "Circle".
  return table === "/" && tableList(table)[index] === "Circle" ? t("symbol.numbered", { name, code }) : name;
}

/** Every symbol that can be chosen: the primary table, then the alternate one. The name is read on
 * demand, so it follows the page's language. */
export const ALL_SYMBOLS: readonly PickSymbol[] = ["/", "\\"].flatMap((table) =>
  tableList(table).flatMap((english, index) =>
    NOT_LISTED.includes(english)
      ? []
      : [
          {
            table,
            code: String.fromCharCode(index + FIRST_CODE),
            get name(): string {
              return nameOf(table, index);
            },
          },
        ],
  ),
);

/** The name of the symbol of this table and code, "" for none. An overlay table is the alternate
 * table. */
export function symbolName(table: string, code: string): string {
  const index = code.length === 1 ? code.charCodeAt(0) - FIRST_CODE : -1;
  const kind = table === "/" ? "/" : "\\";
  return index >= 0 && index < tableList(kind).length && !NOT_LISTED.includes(tableList(kind)[index] ?? "") ? nameOf(kind, index) : "";
}

/** Whether a letter or digit can go over the symbol: the symbols made for it, and any that has one
 * already. */
export function takesOverlay(table: string, code: string): boolean {
  return table !== "/" && (OVERLAY_CHARS.test(table) || OVERLAY_CODES.includes(code));
}

/** The overlay character of a table ("" for the primary and the plain alternate table). */
export function overlayOf(table: string): string {
  return OVERLAY_CHARS.test(table) ? table : "";
}

/** The table for an alternate symbol with this overlay typed: the character in capitals if a digit
 * or letter, else `\` (none). */
export function tableWithOverlay(typed: string): string {
  const char = typed.trim().toUpperCase().slice(0, 1);
  return OVERLAY_CHARS.test(char) ? char : "\\";
}

/** The symbols whose name has every word of the query (a synonym counts for its word) or that are
 * written as the query (`/-`); all for an empty query. */
export function filterSymbols(symbols: readonly PickSymbol[], query: string): PickSymbol[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return [...symbols];
  return symbols.filter(
    (s) => `${s.table}${s.code}` === query.trim() || words.every((w) => s.name.toLowerCase().includes(SYNONYMS[w] ?? w) || s.name.toLowerCase().includes(w)),
  );
}
