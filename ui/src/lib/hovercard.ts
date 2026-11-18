// The card that follows the pointer to a station's marker on the map: after a short delay it shows what matters at a glance (who, how long ago, status, comment, how far and in which direction, the
// temperature of a weather station, how the packets reach us) and goes when the pointer leaves. One element serves every marker, and the aircraft and ships the map draws itself too (`rest`: the map says where
// the thing is and what its box says, lib/layers/card.ts, with the thing's mark before its name). A touch screen has no pointer to rest on a marker, so only a mouse shows it, and a tap opens the full card as ever.
import { t } from "@/i18n";
import { heardWords } from "@/lib/channels";
import { agoWords, bearingText, distanceText } from "@/lib/format";
import { routeWords } from "@/lib/routes";
import { symbolLabel } from "@/lib/stations";
import type { PageRadio } from "@/lib/radios";
import { tempText } from "@/lib/weather";
import type { StationRow } from "@/protocol/protocol";

const DELAY_MS = 250;
const MARGIN = 6; // least distance to the edge of the map
const GAP = 8; // between the marker and the card
const LABEL = 16; // the height of the call under a marker

export interface HoverRow {
  label: string;
  text: string;
}

/** The radios the card names (composables/useRadios.ts `Radios`: every radio in the order of the boxes). */
export type HoverRadios = Readonly<{ all: Readonly<{ value: readonly PageRadio[] }> }>;

const NO_RADIOS: HoverRadios = { all: { value: [] } };

/** The rows the card has for a station: only those that have something to say. "Heard on" says the radios that heard it by their names (with their times while several are on), iGate and Internet; nothing for a
 * station heard on the one radio alone. */
export function hoverRows(row: StationRow, nowMs: number, radios: HoverRadios = NO_RADIOS): HoverRow[] {
  const rows: HoverRow[] = [{ label: t("station.hover.heard"), text: agoWords(row.last_heard, nowMs) }];
  const heard = heardWords(row, radios.all.value, nowMs);
  if (heard !== null) rows.push({ label: t("station.hover.via"), text: heard });
  if (row.last_status !== "") rows.push({ label: t("station.field.status"), text: row.last_status });
  if (row.last_comment !== "") rows.push({ label: t("station.field.comment"), text: row.last_comment });
  if (row.distance_km !== null) {
    rows.push({
      label: t("station.field.from_us"),
      text: t("station.from_us_value", { distance: distanceText(row.distance_km), bearing: bearingText(row.bearing_deg) }),
    });
  }
  if (row.weather !== null && row.weather.temp_c !== null) rows.push({ label: t("weather.temperature"), text: tempText(row.weather.temp_c) });
  if (!row.is_me && row.last_route !== "")
    rows.push({ label: t("station.hover.route"), text: row.last_route === "direct" ? t("station.heard_direct") : routeWords(row.last_route) });
  return rows;
}

function element(tag: string, className: string, text = ""): HTMLElement {
  const node = document.createElement(tag);
  node.className = className;
  node.textContent = text;
  return node;
}

const clamp = (value: number, low: number, high: number): number => Math.max(low, Math.min(high, value));

/** A mark drawn before the title: a path on its box, in the layers' colour or the bad colour. */
interface HoverMark {
  d: string;
  viewBox: string;
  bad: boolean;
}

/** What the card says: a head of two parts (a mark before them, for an aircraft or a ship) and its rows. */
export interface HoverContent {
  title: string;
  sub: string;
  rows: HoverRow[];
  mark?: HoverMark;
}

const SVG = "http://www.w3.org/2000/svg";

/** A mark as the card's head shows it: 16 px, saying nothing to a screen reader (the title does). */
function markElement(mark: HoverMark): SVGSVGElement {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("class", mark.bad ? "hc-mark emergency" : "hc-mark");
  svg.setAttribute("width", "16");
  svg.setAttribute("height", "16");
  svg.setAttribute("viewBox", mark.viewBox);
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS(SVG, "path");
  path.setAttribute("d", mark.d);
  svg.append(path);
  return svg;
}

/** Where on the screen the card's thing is. */
export type HoverBox = Pick<DOMRect, "left" | "top" | "right" | "bottom" | "width">;

/** What the card is shown for: its key (a station's call), where it is, and what it says now (null when it is gone). */
interface Shown {
  key: string;
  box: () => HoverBox;
  content: () => HoverContent | null;
}

export class HoverCard {
  private readonly card = element("div", "hovercard");
  private timer: ReturnType<typeof setTimeout> | null = null;
  private shownFor: Shown | null = null;
  private coming: string | null = null; // (the key the timer is for)

  constructor(
    private readonly container: HTMLElement,
    private readonly lookup: (call: string) => StationRow | undefined,
    private readonly now: () => number,
    private readonly radios: HoverRadios = NO_RADIOS, // (the page's radios: `useRadios()`)
  ) {
    this.card.setAttribute("role", "tooltip");
    this.card.hidden = true;
    container.append(this.card);
  }

  /** Makes the marker show the card for the station when a mouse rests on it. */
  attach(target: HTMLElement, call: string): void {
    target.addEventListener("pointerenter", (event) => {
      if (event.pointerType === "mouse") this.enter({ key: call, box: () => target.getBoundingClientRect(), content: () => this.station(call) });
    });
    target.addEventListener("pointerleave", () => this.hide());
    target.addEventListener("pointerdown", () => this.hide());
  }

  /** A mouse rests on a thing the map draws itself (an aircraft, a ship): the card is shown for it after the delay, and stays while the mouse is on the same thing. */
  rest(key: string, box: () => HoverBox, content: () => HoverContent | null): void {
    if (this.shownFor?.key === key || (this.timer !== null && this.coming === key)) return;
    this.enter({ key, box, content });
  }

  private enter(shown: Shown): void {
    this.cancel();
    this.coming = shown.key;
    this.timer = setTimeout(() => this.show(shown), DELAY_MS);
  }

  private show(shown: Shown): void {
    this.timer = null;
    this.shownFor = shown;
    this.refresh();
  }

  /** What the card says of a station, from its row as it is now. */
  private station(call: string): HoverContent | null {
    const row = this.lookup(call);
    return row ? { title: row.call, sub: symbolLabel(row), rows: hoverRows(row, this.now(), this.radios) } : null;
  }

  /** Writes the card again from what it is shown for as it is now (the age moves on; the row may have changed or gone). */
  refresh(): void {
    const open = this.shownFor;
    const content = open ? open.content() : null;
    if (!open || !content) {
      this.hide();
      return;
    }
    const head = element("div", "hc-head");
    if (content.mark) head.append(markElement(content.mark));
    head.append(element("b", "hc-call", content.title), element("span", "hc-symbol", content.sub));
    const rows = content.rows.map(({ label, text }) => {
      const line = element("div", "hc-row");
      line.append(element("span", "hc-key", label), element("span", "hc-val", text));
      return line;
    });
    this.card.replaceChildren(head, ...rows);
    this.card.hidden = false;
    this.place(open.box());
  }

  /** Above the marker, or below it where there is no room, and inside the map either way. */
  private place(at: HoverBox): void {
    const box = this.container.getBoundingClientRect();
    const { offsetWidth: width, offsetHeight: height } = this.card;
    const above = at.top - box.top - height - GAP;
    const top = above >= MARGIN ? above : at.bottom - box.top + LABEL + GAP;
    this.card.style.left = `${clamp(at.left - box.left + at.width / 2 - width / 2, MARGIN, Math.max(MARGIN, box.width - width - MARGIN))}px`;
    this.card.style.top = `${clamp(top, MARGIN, Math.max(MARGIN, box.height - height - MARGIN))}px`;
  }

  private cancel(): void {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
  }

  hide(): void {
    this.cancel();
    this.shownFor = null;
    this.card.hidden = true;
  }

  /** The marker of the station is gone: so is the card, if it was for that one. */
  release(call: string): void {
    if (this.shownFor?.key === call) this.hide();
  }

  destroy(): void {
    this.hide();
    this.card.remove();
  }
}
