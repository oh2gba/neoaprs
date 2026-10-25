// The page's layout numbers: the tabs of the panel, how wide the panel may be, and the three sizes of the page (phone, tablet, desktop) with how many station cards fit on the map at each. The sizes are decided here, once, from the window
// (composables/useViewport.ts), and the page marks its root with the one it is (`size-phone`, ...): the style sheets of ui/src/styles/ use that class and not media queries of their own, so that the script and the style never disagree.

import { t } from "@/i18n";

export const TAB_IDS = ["messages", "stations", "nearby", "email", "bulletins", "objects", "beacon", "packets", "settings"] as const; // by importance: what a person comes for first, the raw packets and the settings last
export type TabId = (typeof TAB_IDS)[number];

/** The name of a tab, in the language of the page. */
export function tabTitle(id: TabId): string {
  return t(`tab.${id}`);
}

export const PANEL_MIN = 280;
export const PANEL_DEFAULT = 480;
/** From this window width on, a panel the user has not dragged is `PANEL_DEFAULT_WIDE` wide: wide enough for the two columns of the Messages tab and for the nine tabs with their badges (the tab bar turns into a menu when they do not fit). */
const WIDE_WINDOW = 1280;
export const PANEL_DEFAULT_WIDE = 760;

/** The width of the panel of a user who has not dragged it, for a window this wide. */
export function defaultPanelWidth(pageWidth: number): number {
  return pageWidth >= WIDE_WINDOW ? PANEL_DEFAULT_WIDE : PANEL_DEFAULT;
}
/** The panel may take this share of the window... */
const PANEL_MAX_SHARE = 0.8;
/** ...but the map keeps at least this many pixels, so on a narrow window the most is less. */
export const MAP_MIN = 360;
/** What a remembered width may be at the most (the window it is shown in clamps it again). */
export const PANEL_STORED_MAX = 20000;

/**
 * How wide the Messages tab must be (the tab itself, not the window: the panel beside the map can be narrow on a wide screen) to show the list of conversations beside the open conversation.
 * 600 px is a list of 240 px, the divider and a conversation of 359 px, which holds the compose row (the text, "67 left" and Send) and bubbles that can still be read; narrower, one of the two at a time.
 */
export const MESSAGES_WIDE = 600;

/**
 * The Packets tab is a table of five columns while the tab itself (not the window) is at least this wide, and one block for each packet under it: the packet line, then the route and the summary in small text. At the 480 px a panel starts with,
 * the packet column of the table is squeezed until its line breaks letter by letter.
 */
export const PACKETS_TABLE = 520;

/** The widest the panel may be on a page this wide:80 % of it, leaving the map 360 px; never less than the least. */
export function panelMax(pageWidth: number): number {
  return Math.max(PANEL_MIN, Math.min(Math.floor(pageWidth * PANEL_MAX_SHARE), pageWidth - MAP_MIN));
}

/** A panel width, whole pixels, at least PANEL_MIN and at most `panelMax(pageWidth)`. */
export function clampWidth(width: number, pageWidth: number): number {
  return Math.round(Math.max(PANEL_MIN, Math.min(panelMax(pageWidth), width)));
}

export type SizeClass = "phone" | "tablet" | "desktop";

/** A window narrower than this is a phone (a portrait one; a wide window that is short is a phone held sideways: see `SHORT_HEIGHT`). */
const PHONE_MAX = 700;
/** A window narrower than this (and not a phone) is a tablet: the map and the panel side by side, the panel a comfortable fixed width; from here on the panel is the user's to size. */
const TABLET_MAX = 1100;
/** A window shorter than this and narrower than `SHORT_WIDTH` is a phone held sideways (844 by 390, 932 by 430): the tabs and the map take turns there too. */
const SHORT_HEIGHT = 500;
const SHORT_WIDTH = 1000;

export function sizeOf(width: number, height: number): SizeClass {
  if (width < PHONE_MAX || (height < SHORT_HEIGHT && width < SHORT_WIDTH)) return "phone";
  return width < TABLET_MAX ? "tablet" : "desktop";
}

/** The most cards that may be open side by side at each size: one on a phone (a tap replaces it), two on a tablet, four on a desktop; the row that is wider than the map has room for closes its oldest card (components/StationCards.vue), so a narrow map has fewer. */
export function cardCapacity(size: SizeClass): number {
  return size === "phone" ? 1 : size === "tablet" ? 2 : 4;
}

/** What the row of cards leaves free of the map's width (`.cardstack` in ui/src/styles/responsive.css: 10 px at each side), and the gap between two cards. */
export const CARDS_FREE_SIDE = 20;
export const CARD_GAP = 8;
