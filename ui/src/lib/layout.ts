// The page's layout numbers: the panel's tabs, how wide the panel may be, and the three page sizes
// (phone, tablet, desktop) with how many station cards fit at each. Sizes are decided here from the
// window (composables/useViewport.ts) and the root carries the class `size-phone` etc.; style
// sheets use that class, not media queries.

import { t } from "@/i18n";

// ordered by importance: raw packets and settings last
export const TAB_IDS = [
  "messages",
  "stations",
  "nearby",
  "email",
  "bulletins",
  "skeds",
  "objects",
  "beacon",
  "packets",
  "settings",
] as const;
export type TabId = (typeof TAB_IDS)[number];

/** The tabs offered, in TAB_IDS order: HF tests (`skeds`) only while an HF radio is on. */
export function offeredTabs(hfOn: boolean): TabId[] {
  return TAB_IDS.filter((id) => hfOn || id !== "skeds");
}

export function tabTitle(id: TabId): string {
  return t(`tab.${id}`);
}

export const PANEL_MIN = 280;
export const PANEL_DEFAULT = 480;
/**
 * From this window width on, an undragged panel is `PANEL_DEFAULT_WIDE` wide (fits the Messages
 * columns and ten tabs).
 */
const WIDE_WINDOW = 1280;
export const PANEL_DEFAULT_WIDE = 760;

/** The panel width for a user who has not dragged it, for a window this wide. */
export function defaultPanelWidth(pageWidth: number): number {
  return pageWidth >= WIDE_WINDOW ? PANEL_DEFAULT_WIDE : PANEL_DEFAULT;
}
/** The panel may take this share of the window... */
const PANEL_MAX_SHARE = 0.8;
/** ...but the map keeps at least this many pixels, so on a narrow window the most is less. */
export const MAP_MIN = 360;
/** The widest a remembered width may be (the window clamps it again). */
export const PANEL_STORED_MAX = 20000;

/**
 * How wide the Messages tab itself (not the window) must be to show the conversation list beside
 * the open conversation. 600 px is a 240 px list, the divider and a 359 px conversation; narrower
 * shows one at a time.
 */
export const MESSAGES_WIDE = 600;

/**
 * The Packets tab is a five-column table while the tab itself (not the window) is at least this
 * wide; below it each packet is one block. At the default 480 px panel the packet column would be
 * squeezed until its line breaks.
 */
export const PACKETS_TABLE = 520;

/**
 * With several radios on, "Heard on" in the Stations table shows the tags of the two radios that
 * heard a station last while the table is at least this wide, else one, each with "+n" for the
 * rest. On a phone (375 to 430 px) there is room for one eight-letter name and "+n".
 */
export const STATIONS_TWO_RADIOS = 440;

/**
 * The widest the panel may be on a page this wide: 80 %, leaving the map 360 px; never less than
 * the least.
 */
export function panelMax(pageWidth: number): number {
  return Math.max(PANEL_MIN, Math.min(Math.floor(pageWidth * PANEL_MAX_SHARE), pageWidth - MAP_MIN));
}

/** A panel width, whole pixels, at least PANEL_MIN and at most `panelMax(pageWidth)`. */
export function clampWidth(width: number, pageWidth: number): number {
  return Math.round(Math.max(PANEL_MIN, Math.min(panelMax(pageWidth), width)));
}

export type SizeClass = "phone" | "tablet" | "desktop";

/**
 * A window narrower than this is a phone (portrait; a short wide window is a phone sideways, see
 * `SHORT_HEIGHT`).
 */
const PHONE_MAX = 700;
/**
 * A window narrower than this (and not a phone) is a tablet: map and panel side by side, a fixed
 * panel width.
 */
const TABLET_MAX = 1100;
/**
 * A window shorter than this and narrower than `SHORT_WIDTH` is a phone held sideways (844 by 390,
 * 932 by 430).
 */
const SHORT_HEIGHT = 500;
const SHORT_WIDTH = 1000;

export function sizeOf(width: number, height: number): SizeClass {
  if (width < PHONE_MAX || (height < SHORT_HEIGHT && width < SHORT_WIDTH)) return "phone";
  return width < TABLET_MAX ? "tablet" : "desktop";
}

/**
 * The most cards open side by side per size: one on a phone (a tap replaces it), two on a tablet,
 * four on a desktop. A row wider than the map closes its oldest card (components/StationCards.vue),
 * so a narrow map has fewer.
 */
export function cardCapacity(size: SizeClass): number {
  return size === "phone" ? 1 : size === "tablet" ? 2 : 4;
}

/**
 * The map width the card row leaves free (`.cardstack` in ui/src/styles/responsive.css: 10 px a
 * side), and the gap between cards.
 */
export const CARDS_FREE_SIDE = 20;
export const CARD_GAP = 8;
