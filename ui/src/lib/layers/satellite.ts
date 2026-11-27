// The satellites the map draws, from the daemon's `satellites`: each mark where the satellite is now,
// moved between the points the daemon sent; for every open card its track ahead, split where it
// crosses the antimeridian, and its footprint (the circle on the ground from which it is above the
// horizon), drawn as polygons inside -180..180 that close over a pole they cover.
import { clockShift, shiftedTime } from "@/lib/pageclock";
import type { SatelliteCard, SatelliteMark, SatellitePoint, SatellitesMessage } from "@/protocol/protocol";

type Position = [lon: number, lat: number];
const EARTH_KM = 6371.0088;
/** The map's tiles end here: a footprint over a pole is closed along it. */
const EDGE_LAT = 85.0511;
const RING_POINTS = 128;

/** A longitude in -180..180. */
export const wrapLon = (lon: number): number => ((((lon + 180) % 360) + 360) % 360) - 180;

/** The way from one longitude to the next, the short way round. */
const step = (from: number, to: number): number => wrapLon(to - from);

/** Where the satellite is at `nowMs`, between its points; the first before them, null after them. */
export function positionAt(points: readonly SatellitePoint[], nowMs: number): Position | null {
  const first = points[0];
  if (!first) return null;
  if (nowMs <= Date.parse(first.at)) return [first.lon, first.lat];
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1];
    const b = points[i];
    const ta = Date.parse(a.at);
    const tb = Date.parse(b.at);
    if (nowMs <= tb) {
      const f = tb > ta ? (nowMs - ta) / (tb - ta) : 1;
      return [wrapLon(a.lon + f * step(a.lon, b.lon)), a.lat + f * (b.lat - a.lat)];
    }
  }
  return null;
}

/** A line through the positions, cut where it crosses the antimeridian (each piece ends on the edge). */
export function splitLine(line: readonly Position[]): Position[][] {
  const pieces: Position[][] = [];
  let piece: Position[] = [];
  line.forEach((point, i) => {
    const before = line[i - 1];
    if (before && Math.abs(point[0] - before[0]) > 180) {
      const edge = before[0] > 0 ? 180 : -180;
      const far = point[0] + (edge > 0 ? 360 : -360);
      const f = (edge - before[0]) / (far - before[0]);
      const lat = before[1] + f * (point[1] - before[1]);
      piece.push([edge, lat]);
      pieces.push(piece);
      piece = [[-edge, lat]];
    }
    piece.push(point);
  });
  if (piece.length > 1) pieces.push(piece);
  return pieces.filter((one) => one.length > 1);
}

/** The point `km` from a position towards `bearing` (degrees), on the sphere; its longitude is not wrapped. */
function destination(lat: number, lon: number, bearing: number, km: number): Position {
  const rad = Math.PI / 180;
  const d = km / EARTH_KM;
  const p1 = lat * rad;
  const b = bearing * rad;
  const p2 = Math.asin(Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(b));
  const l2 = Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(p1), Math.cos(d) - Math.sin(p1) * Math.sin(p2));
  return [lon + l2 / rad, p2 / rad];
}

/** The part of a ring between two longitudes (Sutherland–Hodgman against each side). */
function clip(ring: readonly Position[], west: number, east: number): Position[] {
  const side = (keep: (p: Position) => boolean, x: number) => (points: readonly Position[]) => {
    const out: Position[] = [];
    points.forEach((p, i) => {
      const q = points[(i + points.length - 1) % points.length];
      const inside = keep(p);
      if (inside !== keep(q)) {
        const f = (x - q[0]) / (p[0] - q[0]);
        out.push([x, q[1] + f * (p[1] - q[1])]);
      }
      if (inside) out.push(p);
    });
    return out;
  };
  return side((p) => p[0] <= east, east)(side((p) => p[0] >= west, west)(ring));
}

const clampLat = (p: Position): Position => [p[0], Math.max(-EDGE_LAT, Math.min(EDGE_LAT, p[1]))];

/**
 * The footprint round a position: the polygons (outer rings, closed) that together cover it inside
 * -180..180. A circle over a pole runs round the world and is closed along the map's edge.
 */
export function footprintRings(lat: number, lon: number, km: number): Position[][] {
  if (km <= 0) return [];
  const ring: Position[] = [];
  for (let i = 0; i < RING_POINTS; i++) {
    const point = destination(lat, lon, (360 * i) / RING_POINTS, km);
    const before = ring[ring.length - 1];
    ring.push(before ? [before[0] + step(before[0], point[0]), point[1]] : point);
  }
  const reach = (km / EARTH_KM) * (180 / Math.PI);
  const pole = lat + reach > 90 ? EDGE_LAT : lat - reach < -90 ? -EDGE_LAT : null;
  if (pole !== null) {
    // the ring goes once round the world: close it along the edge on the pole's side
    const last = ring[ring.length - 1];
    const first = ring[0];
    const end = first[0] + (last[0] > first[0] ? 360 : -360);
    ring.push([end, first[1]], [end, pole], [first[0], pole]);
  }
  const flat = ring.map(clampLat);
  const pieces: Position[][] = [];
  for (const shift of [-720, -360, 0, 360, 720]) {
    const part = clip(
      flat.map(([x, y]): Position => [x + shift, y]),
      -180,
      180,
    );
    if (part.length >= 3) pieces.push([...part, part[0]]);
  }
  return pieces;
}

interface Feature<G, P> {
  type: "Feature";
  geometry: G;
  properties: P;
}
interface Collection<G, P> {
  type: "FeatureCollection";
  features: Feature<G, P>[];
}

export interface SatelliteFeatures {
  marks: Collection<{ type: "Point"; coordinates: Position }, { id: number; name: string; open: boolean }>;
  tracks: Collection<{ type: "MultiLineString"; coordinates: Position[][] }, { id: number }>;
  footprints: Collection<{ type: "MultiPolygon"; coordinates: Position[][][] }, { id: number }>;
}

export const NO_SATELLITES: SatelliteFeatures = {
  marks: { type: "FeatureCollection", features: [] },
  tracks: { type: "FeatureCollection", features: [] },
  footprints: { type: "FeatureCollection", features: [] },
};

/** The track of a card from where the satellite is now. */
function trackAhead(card: SatelliteCard, here: Position, nowMs: number): Position[] {
  const ahead = card.track.filter((point) => Date.parse(point.at) > nowMs).map((p): Position => [p.lon, p.lat]);
  return [here, ...ahead];
}

/** Every satellite's mark where it is at `nowMs`, between its points. */
export function satelliteMarks(
  marks: readonly SatelliteMark[],
  cards: readonly SatelliteCard[],
  nowMs: number,
): SatelliteFeatures["marks"] {
  const open = new Set(cards.map((card) => card.id));
  const features: SatelliteFeatures["marks"]["features"] = [];
  for (const mark of marks) {
    const at = positionAt(mark.points, nowMs);
    if (!at) continue;
    features.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: at },
      properties: { id: mark.id, name: mark.name, open: open.has(mark.id) },
    });
  }
  return { type: "FeatureCollection", features };
}

/** Whether two drawings of the marks have the same satellites in the same places. */
export function sameMarks(a: SatelliteFeatures["marks"], b: SatelliteFeatures["marks"]): boolean {
  if (a.features.length !== b.features.length) return false;
  return a.features.every((one, i) => {
    const other = b.features[i];
    return (
      one.properties.id === other.properties.id &&
      one.properties.open === other.properties.open &&
      one.geometry.coordinates[0] === other.geometry.coordinates[0] &&
      one.geometry.coordinates[1] === other.geometry.coordinates[1]
    );
  });
}

/** What the map draws now: every mark, and the track and footprint of each open card. */
export function satelliteFeatures(
  marks: readonly SatelliteMark[],
  cards: readonly SatelliteCard[],
  nowMs: number,
): SatelliteFeatures {
  const drawn = satelliteMarks(marks, cards, nowMs);
  const here = new Map<number, Position>(
    drawn.features.map((feature) => [feature.properties.id, feature.geometry.coordinates]),
  );
  const tracks: SatelliteFeatures["tracks"]["features"] = [];
  const footprints: SatelliteFeatures["footprints"]["features"] = [];
  for (const card of cards) {
    const at = here.get(card.id);
    if (!at) continue;
    tracks.push({
      type: "Feature",
      geometry: { type: "MultiLineString", coordinates: splitLine(trackAhead(card, at, nowMs)) },
      properties: { id: card.id },
    });
    footprints.push({
      type: "Feature",
      geometry: {
        type: "MultiPolygon",
        coordinates: footprintRings(at[1], at[0], card.footprint_km).map((ring) => [ring]),
      },
      properties: { id: card.id },
    });
  }
  return {
    marks: drawn,
    tracks: { type: "FeatureCollection", features: tracks },
    footprints: { type: "FeatureCollection", features: footprints },
  };
}

/** The message with its times on the page's clock (lib/pageclock.ts); one whose `at` is no time is left as it is. */
export function satellitesInPageClock(message: SatellitesMessage, nowMs: number): SatellitesMessage {
  const shift = clockShift(message.at, nowMs);
  if (shift === null || shift === 0) return message;
  const move = (iso: string): string => shiftedTime(iso, shift);
  const points = (list: readonly SatellitePoint[]): SatellitePoint[] =>
    list.map((one) => ({ ...one, at: move(one.at) }));
  return {
    ...message,
    at: move(message.at),
    satellites: message.satellites.map((one) => ({ ...one, points: points(one.points) })),
    cards: message.cards.map((card) => ({
      ...card,
      track: points(card.track),
      next_pass: card.next_pass && {
        ...card.next_pass,
        rise: move(card.next_pass.rise),
        set: move(card.next_pass.set),
        max_at: move(card.next_pass.max_at),
      },
      looks: card.looks.map((one) => ({ ...one, at: move(one.at) })),
    })),
  };
}
