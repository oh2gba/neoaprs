// How a station's packets reach us, drawn on the map: at most two routes, the latest packet's
// (solid) and the latest earlier packet that came another way (greyed). The daemon keeps just
// these (`route_marks`, newest first, each with the station's place when heard).
// A packet heard on the radio runs from the station through each digipeater with a position to
// our station. A third-party packet starts at the iGate that put it on the air. A packet an iGate
// put on the internet runs from the station through its digipeaters to the iGate, which ends the
// line with its call and an internet mark (or at the last digipeater with a position). A packet
// heard direct, or one never on the air (an app), has no line. A hop without a position is skipped.
// `routeHops` reads the daemon's route text (`last_route`: "via OH2RCH-1 → OH2RCH-3",
// "via OH7JHF-1 (internet) → OH2RCH-3").
import { t } from "@/i18n";
import { unwrapLine } from "@/lib/dateline";
import { hasPosition } from "@/lib/stations";
import type { StationRow } from "@/protocol/protocol";

type LonLat = [number, number];
type Mark = StationRow["route_marks"][number];

interface RouteLine {
  type: "Feature";
  properties: { call: string; previous: number };
  geometry: { type: "LineString"; coordinates: LonLat[] };
}

interface RouteDot {
  type: "Feature";
  /** `label` is written beside the dot; `end` is 1 for the iGate that ends a line */
  properties: { call: string; label: string; previous: number; end: number };
  geometry: { type: "Point"; coordinates: LonLat };
}

export interface RouteCollection {
  type: "FeatureCollection";
  features: (RouteLine | RouteDot)[];
}

interface Hops {
  /** the iGate that put a third-party packet on the air; the line starts there */
  gate: string | null;
  hops: string[];
}

const GATE_SUFFIX = " (internet)";

/** The calls of a route in the daemon's wording; null for a station heard direct or none. */
export function routeHops(text: string): Hops | null {
  if (!text.startsWith("via ")) return null;
  const calls = text.slice(4).split(" → ");
  const first = calls[0] ?? "";
  if (!first.endsWith(GATE_SUFFIX)) return { gate: null, hops: calls };
  return { gate: first.slice(0, -GATE_SUFFIX.length), hops: calls.slice(1) };
}

function placeOf(stations: ReadonlyMap<string, StationRow>, call: string): LonLat | null {
  const row = stations.get(call);
  return row && hasPosition(row) ? [row.lon, row.lat] : null;
}

/** Where the station was when the packet was heard, else where it is now; null if unknown. */
function startOf(row: StationRow, mark: Mark): LonLat | null {
  if (mark.lat !== null && mark.lon !== null) return [mark.lon, mark.lat];
  return hasPosition(row) ? [row.lon, row.lat] : null;
}

/** The line of one route and the dots on it; null if there is no line to draw. */
function oneRoute(row: StationRow, mark: Mark, stations: ReadonlyMap<string, StationRow>, us: LonLat, previous: number): RouteCollection["features"] | null {
  if (mark.kind === "app") return null;
  const gated = mark.kind === "gated";
  const named = (gated ? [mark.gate, ...mark.hops] : mark.hops).flatMap((call) => {
    const at = placeOf(stations, call);
    return at ? [{ call, at }] : [];
  });
  const start = gated ? null : startOf(row, mark);
  if (!gated && start === null) return null;
  if (mark.kind === "rf" && mark.hops.length === 0) return null;
  const end = mark.kind === "igate" ? placeOf(stations, mark.gate) : us;
  const line = [...(start ? [start] : []), ...named.map((hop) => hop.at), ...(end ? [end] : [])];
  if (line.length < 2) return null;
  const dots: RouteDot[] = named.map(({ call, at }) => ({
    type: "Feature",
    properties: { call, label: call, previous, end: 0 },
    geometry: { type: "Point", coordinates: at },
  }));
  if (mark.kind === "igate" && end) {
    const label = t("route.igate_label", { call: mark.gate });
    dots.push({ type: "Feature", properties: { call: mark.gate, label, previous, end: 1 }, geometry: { type: "Point", coordinates: end } });
  }
  return [{ type: "Feature", properties: { call: row.call, previous }, geometry: { type: "LineString", coordinates: unwrapLine(line) } }, ...dots];
}

/**
 * The latest packet's route line and, apart, the earlier one that came another way (`previous`,
 * greyed); empty with no station, no home place or no route.
 */
export function routeFeatures(
  row: StationRow | undefined,
  stations: ReadonlyMap<string, StationRow>,
  home: { lat: number; lon: number } | null,
): RouteCollection {
  const features: RouteCollection["features"] = [];
  if (row && home && !row.is_me) {
    const us: LonLat = [home.lon, home.lat];
    const drawn = new Set<string>();
    row.route_marks.slice(0, 2).forEach((mark, index) => {
      for (const f of oneRoute(row, mark, stations, us, index) ?? []) {
        if (f.geometry.type === "LineString") features.push(f);
        else if (!drawn.has(f.properties.call)) {
          drawn.add(f.properties.call);
          features.push(f);
        }
      }
    });
  }
  return { type: "FeatureCollection", features };
}
