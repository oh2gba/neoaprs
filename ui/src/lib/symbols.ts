// The APRS symbols: a table character and a code character name a picture in the sprite sheets of public/symbols/ (the aprs.fi set of OH7LZB, see public/symbols/SOURCE.txt). Each sheet is
// 16 symbols wide and 6 high, SPRITE_PX pixels a symbol, the codes "!" (0x21) to "~" (0x7E) in order from the top left. The overlay sheet has the characters 0-9 and A-Z at the places
// of the codes of the same characters, white with a shadow: an overlay table draws the alternate symbol of the code and the overlay character of the table over it.

import { hasMessage, t } from "@/i18n";
import { LIMITS, MOBILE_SYMBOLS } from "@/protocol/lists";

export const SPRITE_PX = 48;
export const SPRITE_COLUMNS = 16;
export const SPRITE_ROWS = 6;
const SYMBOL_DIR = "symbols";

type Sheet = "primary" | "alternate" | "overlay";

interface SpriteLayer {
  sheet: Sheet;
  /** the place of the symbol in the sheet, in sprite cells */
  column: number;
  row: number;
}

const FIRST_CODE = 0x21;
const LAST_CODE = 0x7e;
const OVERLAYS = /^[0-9A-Z]$/;

/** The cell of a code character in a sheet, null for a character that has none. */
export function cellOf(char: string): { column: number; row: number } | null {
  if (char.length !== 1) return null;
  const code = char.charCodeAt(0);
  if (code < FIRST_CODE || code > LAST_CODE) return null;
  const index = code - FIRST_CODE;
  return { column: index % SPRITE_COLUMNS, row: Math.floor(index / SPRITE_COLUMNS) };
}

/** The pictures to stack, bottom first, for a symbol: the primary or alternate sprite, with the overlay character on top for an overlay table. Empty for a symbol that is none (a station whose position was never heard). */
export function symbolLayers(table: string, code: string): SpriteLayer[] {
  const cell = cellOf(code);
  if (cell === null) return [];
  if (table === "/") return [{ sheet: "primary", ...cell }];
  if (table === "\\") return [{ sheet: "alternate", ...cell }];
  const over = OVERLAYS.test(table) ? cellOf(table) : null;
  return over === null
    ? []
    : [
        { sheet: "alternate", ...cell },
        { sheet: "overlay", ...over },
      ];
}

/** The address of a sheet. */
export function sheetUrl(sheet: Sheet): string {
  return `${SYMBOL_DIR}/${sheet}.png`;
}

/** The CSS of one layer drawn `size` pixels wide: the sheet as the background, moved to the cell. */
export function layerStyle(layer: SpriteLayer, size: number): Record<string, string> {
  return {
    backgroundImage: `url(${sheetUrl(layer.sheet)})`,
    backgroundSize: `${SPRITE_COLUMNS * size}px ${SPRITE_ROWS * size}px`,
    backgroundPosition: `${-layer.column * size}px ${-layer.row * size}px`,
  };
}

/** The name of the symbol of a table and a code in the page's language ("Car", "Digipeater"), "unknown" for none: the catalogue has a message for each of the codes `!` to `~` of the two tables (`symbol.primary.3e`, written from the daemon's own list); an overlay table is the alternate one. */
export function symbolText(table: string, code: string): string {
  const known = table === "/" || table === "\\" || OVERLAYS.test(table);
  const id = `symbol.${table === "/" ? "primary" : "alternate"}.${code.length === 1 ? code.charCodeAt(0).toString(16) : ""}`;
  return known && hasMessage(id) ? t(id) : t("symbol.unknown");
}

/** Whether a symbol is the one of a station that moves or is carried (a car, a bike, a jogger, a boat, an aircraft ...), by the daemon's own list (MOBILE_SYMBOLS): in either table and with any overlay, false for any other. */
export function isMobileSymbol(table: string, code: string): boolean {
  const known = table === "/" || table === "\\" || OVERLAYS.test(table);
  return known && code.length === 1 && (table === "/" ? MOBILE_SYMBOLS.primary : MOBILE_SYMBOLS.alternate).includes(code);
}

/** The path that is recommended for a station with this symbol, which an empty path setting means: WIDE1-1,WIDE2-1 for a mobile symbol, WIDE2-1 (no fill-in hop) for any other, a fixed station. */
export function recommendedPath(table: string, code: string): string {
  return isMobileSymbol(table, code) ? LIMITS.path.recommendedMobile : LIMITS.path.recommendedFixed;
}
