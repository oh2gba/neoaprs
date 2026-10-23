// How a station's packets reach us, drawn on the map: a line from the station through each digipeater of its latest route that has a position to our own station, and, when the route most of its
// packets came by is another one, that route too. The routes come from the station row as the daemon words them (`last_route`, `best_route`: "direct", "via OH2RCH-2", "via OH2RCH-1 → OH2RCH-3",
// "via OH7JHF-1 (internet) → OH2RCH-3"); a hop with no position (`?` or a station we have not placed) is left out and the line goes on to the next. A latest packet that was a copy an iGate gated
// back from the internet says nothing of how the station reaches us by radio: then the best route (which counts no such copies), when there is one, is the line, drawn as the latest one is.
import { hasPosition } from "@/lib/stations";
import type { StationRow } from "@/protocol/protocol";

type LonLat = [number, number];

interface RouteLine {
  type: "Feature";
  properties: { call: string; best: number };
  geometry: { type: "LineString"; coordinates: LonLat[] };
}

interface RouteDot {
  type: "Feature";
  properties: { call: string; best: number };
  geometry: { type: "Point"; coordinates: LonLat };
}

export interface RouteCollection {
  type: "FeatureCollection";
  features: (RouteLine | RouteDot)[];
}

interface Hops {
  /** the iGate that put a third-party packet on the air; the line starts there, as the station itself was not heard */
  gate: string | null;
  hops: string[];
}

const GATE_SUFFIX = " (internet)";

/** The calls of a route as the wire words it; null for a station heard direct and for none. */
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

/** The line of one route and the digipeaters on it that have a position; null when it would not reach us. */
function oneRoute(row: StationRow, text: string, stations: ReadonlyMap<string, StationRow>, us: LonLat, best: number): RouteCollection["features"] | null {
  const route = routeHops(text);
  if (route === null) return null;
  const through = (route.gate === null ? route.hops : [route.gate, ...route.hops]).flatMap((call) => {
    const at = placeOf(stations, call);
    return at ? [{ call, at }] : [];
  });
  const start: LonLat[] = route.gate === null && hasPosition(row) ? [[row.lon, row.lat]] : [];
  const line = [...start, ...through.map((hop) => hop.at), us];
  if (line.length < 2 || (route.gate === null && start.length === 0)) return null;
  const dots: RouteDot[] = through.map(({ call, at }) => ({ type: "Feature", properties: { call, best }, geometry: { type: "Point", coordinates: at } }));
  return [{ type: "Feature", properties: { call: row.call, best }, geometry: { type: "LineString", coordinates: line } }, ...dots];
}

/** The latest route of the station and, when it differs, the best one (marked `best`, drawn fainter); empty with no station, no place of ours or no route to draw. */
export function routeFeatures(
  row: StationRow | undefined,
  stations: ReadonlyMap<string, StationRow>,
  home: { lat: number; lon: number } | null,
): RouteCollection {
  const features: RouteCollection["features"] = [];
  if (row && home && !row.is_me) {
    const us: LonLat = [home.lon, home.lat];
    const gated = routeHops(row.last_route)?.gate != null;
    const latest = gated && routeHops(row.best_route) !== null ? row.best_route : row.last_route; // (with no radio route known, the gate's is all there is)
    features.push(...(oneRoute(row, latest, stations, us, 0) ?? []));
    if (row.best_route !== latest) {
      const seen = new Set(features.filter((f) => f.geometry.type === "Point").map((f) => f.properties.call));
      for (const f of oneRoute(row, row.best_route, stations, us, 1) ?? []) {
        if (f.geometry.type === "LineString" || !seen.has(f.properties.call)) features.push(f);
      }
    }
  }
  return { type: "FeatureCollection", features };
}
