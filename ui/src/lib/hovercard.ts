// The card that follows the pointer to a station's marker on the map: after a short delay it shows what matters at a glance (who, how long ago, status, comment, how far and in which direction, the
// temperature of a weather station, how the packets reach us) and goes when the pointer leaves. One element serves every marker. A touch screen has no pointer to rest on a marker, so only a mouse
// shows it, and a tap opens the full card as ever.
import { ageText, bearingText, distanceText } from "@/lib/format";
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

/** The rows the card has for a station: only those that have something to say. */
export function hoverRows(row: StationRow, nowMs: number): HoverRow[] {
  const rows: HoverRow[] = [{ label: "Heard", text: `${ageText(row.last_heard, nowMs)} ago` }];
  if (row.last_status !== "") rows.push({ label: "Status", text: row.last_status });
  if (row.last_comment !== "") rows.push({ label: "Comment", text: row.last_comment });
  if (row.distance_km !== null) rows.push({ label: "From us", text: `${distanceText(row.distance_km)} km, ${bearingText(row.bearing_deg)}` });
  if (row.weather !== null && row.weather.temp_c !== null) rows.push({ label: "Temperature", text: tempText(row.weather.temp_c) });
  if (!row.is_me && row.last_route !== "") rows.push({ label: "Route", text: row.last_route === "direct" ? "heard direct" : row.last_route });
  return rows;
}

function element(tag: string, className: string, text = ""): HTMLElement {
  const node = document.createElement(tag);
  node.className = className;
  node.textContent = text;
  return node;
}

const clamp = (value: number, low: number, high: number): number => Math.max(low, Math.min(high, value));

export class HoverCard {
  private readonly card = element("div", "hovercard");
  private timer: ReturnType<typeof setTimeout> | null = null;
  private shownFor: { call: string; target: HTMLElement } | null = null;

  constructor(
    private readonly container: HTMLElement,
    private readonly lookup: (call: string) => StationRow | undefined,
    private readonly now: () => number,
  ) {
    this.card.setAttribute("role", "tooltip");
    this.card.hidden = true;
    container.append(this.card);
  }

  /** Makes the marker show the card for the station when a mouse rests on it. */
  attach(target: HTMLElement, call: string): void {
    target.addEventListener("pointerenter", (event) => {
      if (event.pointerType === "mouse") this.enter(target, call);
    });
    target.addEventListener("pointerleave", () => this.hide());
    target.addEventListener("pointerdown", () => this.hide());
  }

  private enter(target: HTMLElement, call: string): void {
    this.cancel();
    this.timer = setTimeout(() => this.show(target, call), DELAY_MS);
  }

  private show(target: HTMLElement, call: string): void {
    this.timer = null;
    this.shownFor = { call, target };
    this.refresh();
  }

  /** Writes the card again from the station's row as it is now (the age moves on; the row may have changed or gone). */
  refresh(): void {
    const open = this.shownFor;
    const row = open ? this.lookup(open.call) : undefined;
    if (!open || !row) {
      this.hide();
      return;
    }
    const head = element("div", "hc-head");
    head.append(element("b", "hc-call", row.call), element("span", "hc-symbol", `${row.symbol_name}${row.own ? " (ours)" : ""}`));
    const rows = hoverRows(row, this.now()).map(({ label, text }) => {
      const line = element("div", "hc-row");
      line.append(element("span", "hc-key", label), element("span", "hc-val", text));
      return line;
    });
    this.card.replaceChildren(head, ...rows);
    this.card.hidden = false;
    this.place(open.target);
  }

  /** Above the marker, or below it where there is no room, and inside the map either way. */
  private place(target: HTMLElement): void {
    const box = this.container.getBoundingClientRect();
    const at = target.getBoundingClientRect();
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
    if (this.shownFor?.call === call) this.hide();
  }

  destroy(): void {
    this.hide();
    this.card.remove();
  }
}
