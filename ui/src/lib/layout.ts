// The page's layout numbers: the tabs of the panel and how wide the panel may be. (Under 800 px of page the panel goes under the map: that is the media query of style.css.)

export const TAB_IDS = ["stations", "packets", "messages", "email", "bulletins", "objects", "beacon", "tnc", "settings"] as const;
export type TabId = (typeof TAB_IDS)[number];

export const TAB_TITLES: Record<TabId, string> = {
  stations: "Stations",
  packets: "Packets",
  messages: "Messages",
  email: "Email",
  bulletins: "Bulletins",
  objects: "Objects",
  beacon: "Beacon",
  tnc: "TNC",
  settings: "Settings",
};

export const PANEL_MIN = 280;
export const PANEL_DEFAULT = 480;
/** The panel may take this share of the window... */
const PANEL_MAX_SHARE = 0.8;
/** ...but the map keeps at least this many pixels, so on a narrow window the most is less. */
export const MAP_MIN = 360;
/** What a remembered width may be at the most (the window it is shown in clamps it again). */
export const PANEL_STORED_MAX = 20000;

/** The widest the panel may be on a page this wide: 80 % of it, leaving the map 360 px; never less than the least. */
export function panelMax(pageWidth: number): number {
  return Math.max(PANEL_MIN, Math.min(Math.floor(pageWidth * PANEL_MAX_SHARE), pageWidth - MAP_MIN));
}

/** A panel width, whole pixels, at least PANEL_MIN and at most `panelMax(pageWidth)`. */
export function clampWidth(width: number, pageWidth: number): number {
  return Math.round(Math.max(PANEL_MIN, Math.min(panelMax(pageWidth), width)));
}
