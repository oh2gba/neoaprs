// The marker of a station on the map as DOM nodes (the call is text, never markup): the APRS symbol as sprite layers, the call under it, the characters a signpost shows on its sign, classes for our own station and our own objects, the selected one and
// how dim it is, a ring for a station heard direct within the hour and a dotted outline with an italic call for a station known from the internet alone. The map (components/StationMap.vue) puts the element at the station's position; styles are in ui/src/styles/map.css.
import { t } from "@/i18n";
import type { StationRow } from "@/protocol/protocol";
import { MARKER_STEPS } from "@/lib/aging";
import { internetOnly } from "@/lib/channels";
import { symbolLabel } from "@/lib/stations";
import { layerStyle, symbolLayers } from "@/lib/symbols";
import { markerWeather } from "@/lib/weather";

const MARKER_PX = 26;

export interface MarkerDom {
  root: HTMLElement;
  icon: HTMLElement;
  /** the 1 to 3 characters a signpost shows over its symbol; empty (and so not shown) for any other station */
  sign: HTMLElement;
  label: HTMLElement;
  /** the symbol the icon shows now (null before the first paint), so that its layers are made again only when it changes */
  symbol: string | null;
}

export function buildMarkerDom(): MarkerDom {
  const root = document.createElement("div");
  root.className = "stn";
  root.setAttribute("role", "button"); // the hover card (lib/hovercard.ts) is the tooltip, so the name is for a screen reader
  const icon = document.createElement("div");
  icon.className = "stn-icon";
  const sign = document.createElement("span");
  sign.className = "stn-sign";
  const label = document.createElement("span");
  label.className = "stn-label";
  root.append(icon, sign, label);
  return { root, icon, sign, label, symbol: null };
}

interface MarkerState {
  /** how dim the marker is, 0 fresh to MARKER_STEPS - 1 nearest the timeout (lib/aging.ts) */
  fade: number;
  selected: boolean;
  /** a packet of the station was heard direct within the last hour (lib/routes.ts): a ring round the symbol */
  direct: boolean;
}

/** Makes the element show the row: the symbol, the call, the classes. */
export function paintMarker(dom: MarkerDom, row: StationRow, state: MarkerState): void {
  const symbol = `${row.symbol_table}${row.symbol_code}`;
  if (symbol !== dom.symbol) {
    dom.symbol = symbol;
    dom.icon.replaceChildren(
      ...symbolLayers(row.symbol_table, row.symbol_code).map((layer) => {
        const part = document.createElement("span");
        part.className = "stn-layer";
        Object.assign(part.style, layerStyle(layer, MARKER_PX));
        return part;
      }),
    );
    dom.icon.classList.toggle("stn-plain", dom.icon.childElementCount === 0);
  }
  if (dom.label.textContent !== row.call) dom.label.textContent = row.call;
  const sign = row.sign ?? "";
  if (dom.sign.textContent !== sign) dom.sign.textContent = sign;
  dom.root.classList.toggle("stn--sign", sign !== "");
  const net = internetOnly(row);
  const details = [symbolLabel(row), markerWeather(row), state.direct ? t("station.heard_direct") : "", net ? t("station.marker.internet") : ""].filter(
    (part) => part !== "",
  );
  dom.root.setAttribute("aria-label", t("station.marker_label", { call: row.call, details: details.join(", ") }));
  dom.root.classList.toggle("stn--me", row.is_me);
  dom.root.classList.toggle("stn--own", row.own);
  dom.root.classList.toggle("stn--selected", state.selected);
  dom.root.classList.toggle("stn--direct", state.direct);
  dom.root.classList.toggle("stn--net", net);
  for (let step = 1; step < MARKER_STEPS; step++) dom.root.classList.toggle(`stn--fade-${step}`, state.fade === step);
}
