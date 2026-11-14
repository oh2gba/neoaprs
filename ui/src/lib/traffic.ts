// The ships and the aircraft of the map in the page's words: what the map layers draw for each (lib/trafficlayers.ts: the icon by the type, turned the way the bow or the track points, and the full name beside it), the facts of the
// card that a click opens (components/TrafficCard.vue), and the status row under each switch of the Settings tab (components/TrafficStatus.vue). They are only received over the internet: nothing here sends anything.
// The units are the sea's and the air's own: knots, feet, the degrees of a heading; a metric figure follows in brackets where a reader may want it.
import { formatNumber, t } from "@/i18n";
import { NONE, agoWords, bearingText, dateTimeText, distanceText, hourMinuteText, positionText } from "@/lib/format";
import type { AircraftRow, FeedState, ShipRow } from "@/protocol/protocol";

export type TrafficKind = "ship" | "aircraft";
/** What the card shows: a ship by its MMSI or an aircraft by its ICAO address, as the topics key them. */
export interface TrafficPick {
  kind: TrafficKind;
  key: string;
}

const KMH_PER_KN = 1.852;
const M_PER_FT = 0.3048;
/** The sources by their own names, the same in every language. */
const SOURCES = { ais: "Digitraffic", adsb: "adsb.fi" } as const;

interface TrafficProps {
  key: string;
  icon: string;
  /** degrees clockwise from north; 0 for an icon that points nowhere (a round one) */
  rotate: number;
  label: string;
  picked: 0 | 1;
}
interface PointFeature {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: TrafficProps;
}
export interface TrafficCollection {
  type: "FeatureCollection";
  features: PointFeature[];
}

/** The name the map and the card give a ship: its own, in full, else its MMSI. */
export function shipName(row: ShipRow): string {
  return row.name || t("traffic.card.unnamed", { mmsi: row.mmsi });
}

/** The name of an aircraft: the call sign it flies under, else its registration, else its ICAO address. */
export function aircraftName(row: AircraftRow): string {
  return row.flight || row.registration || row.hex.toUpperCase();
}

/** The icon of a ship: the hull in the colour of its group, pointed the way it heads; a round one for a still ship whose bow is not known. */
function shipIcon(row: ShipRow): string {
  return `ship-${row.category}${row.bearing_deg === null ? "-still" : ""}`;
}

/** The icon of an aircraft by its kind; one that declares an emergency is drawn in the colour of an alert. */
function aircraftIcon(row: AircraftRow): string {
  return `aircraft-${row.kind}${row.emergency ? "-alert" : ""}`;
}

const point = (lat: number, lon: number, properties: TrafficProps): PointFeature => ({
  type: "Feature",
  geometry: { type: "Point", coordinates: [lon, lat] },
  properties,
});

export function shipFeatures(rows: Iterable<ShipRow>, picked: string | null): TrafficCollection {
  const features: PointFeature[] = [];
  for (const row of rows) {
    const key = String(row.mmsi);
    features.push(point(row.lat, row.lon, { key, icon: shipIcon(row), rotate: row.bearing_deg ?? 0, label: shipName(row), picked: key === picked ? 1 : 0 }));
  }
  return { type: "FeatureCollection", features };
}

export function aircraftFeatures(rows: Iterable<AircraftRow>, picked: string | null): TrafficCollection {
  const features: PointFeature[] = [];
  for (const row of rows) {
    features.push(
      point(row.lat, row.lon, {
        key: row.hex,
        icon: aircraftIcon(row),
        rotate: row.track_deg ?? 0,
        label: aircraftName(row),
        picked: row.hex === picked ? 1 : 0,
      }),
    );
  }
  return { type: "FeatureCollection", features };
}

export interface Fact {
  label: string;
  value: string;
}

const knots = (kn: number | null): string => (kn === null ? NONE : `${formatNumber(kn, 1)} kn`);
const knotsAndKmh = (kn: number | null): string => (kn === null ? NONE : `${Math.round(kn)} kn (${Math.round(kn * KMH_PER_KN)} km/h)`);
const metres = (m: number | null, digits = 0): string => (m === null ? NONE : `${formatNumber(m, digits)} m`);
const fact = (id: Parameters<typeof t>[0], value: string): Fact => ({ label: t(id), value });
/** Only the facts that say something: one whose value is none is left out. */
const said = (facts: Fact[]): Fact[] => facts.filter((f) => f.value !== "" && f.value !== NONE);

function shipSize(row: ShipRow): string {
  if (row.length_m !== null && row.beam_m !== null) return t("traffic.value.size", { length: row.length_m, beam: row.beam_m });
  return metres(row.length_m);
}

/** The facts of a ship's card, in the order a reader wants them. */
export function shipFacts(row: ShipRow, nowMs: number): Fact[] {
  return said([
    fact("traffic.fact.type", t(`traffic.ship.kind.${row.kind}`)),
    fact("traffic.fact.mmsi", String(row.mmsi)),
    fact("traffic.fact.call_sign", row.call_sign),
    fact("traffic.fact.imo", row.imo === null ? "" : String(row.imo)),
    fact("traffic.fact.status", row.nav_status === null ? "" : navStatus(row.nav_status)),
    fact("traffic.fact.speed", knots(row.speed_kn)),
    fact("traffic.fact.course", bearingText(row.course_deg)),
    fact("traffic.fact.heading", row.heading_deg === null ? "" : `${row.heading_deg}°`),
    fact("traffic.fact.size", shipSize(row)),
    fact("traffic.fact.draught", metres(row.draught_m, 1)),
    fact("traffic.fact.destination", row.destination),
    fact("traffic.fact.eta", dateTimeText(row.eta).slice(0, 16)),
    fact("traffic.fact.distance", `${distanceText(row.distance_km)} km`),
    fact("traffic.fact.position", positionText(row.lat, row.lon, 4)),
    fact("traffic.fact.heard", agoWords(row.position_at, nowMs)),
  ]);
}

/** The words of a navigational status of AIS; a code the page has no words for is shown as its number. */
function navStatus(code: number): string {
  const id = `traffic.ship.nav.${code}`;
  return [0, 1, 2, 3, 4, 5, 6, 7, 8, 11, 12, 14].includes(code) ? t(id as Parameters<typeof t>[0]) : String(code);
}

function altitude(row: AircraftRow): string {
  if (row.on_ground) return t("traffic.value.ground");
  return row.altitude_ft === null ? NONE : `${formatNumber(row.altitude_ft, 0)} ft (${formatNumber(Math.round(row.altitude_ft * M_PER_FT), 0)} m)`;
}

function aircraftType(row: AircraftRow): string {
  const kind = t(`traffic.aircraft.kind.${row.kind}`);
  if (row.description && row.type_code) return `${row.description} (${row.type_code})`;
  return row.description || row.type_code || kind;
}

/** The facts of an aircraft's card. */
export function aircraftFacts(row: AircraftRow, nowMs: number): Fact[] {
  return said([
    fact("traffic.fact.emergency", row.emergency ? t(`traffic.aircraft.emergency.${row.emergency}` as Parameters<typeof t>[0]) : ""),
    fact("traffic.fact.type", aircraftType(row)),
    fact("traffic.fact.flight", row.flight),
    fact("traffic.fact.registration", row.registration),
    fact("traffic.fact.address", row.hex.toUpperCase()),
    fact("traffic.fact.altitude", altitude(row)),
    fact("traffic.fact.speed", knotsAndKmh(row.speed_kn)),
    fact("traffic.fact.track", bearingText(row.track_deg)),
    fact("traffic.fact.vertical", row.vertical_fpm === null || row.on_ground ? "" : `${formatNumber(row.vertical_fpm, 0)} ft/min`),
    fact("traffic.fact.squawk", row.squawk),
    fact("traffic.fact.distance", `${distanceText(row.distance_km)} km`),
    fact("traffic.fact.position", positionText(row.lat, row.lon, 4)),
    fact("traffic.fact.heard", agoWords(row.position_at, nowMs)),
  ]);
}

/** The title of the card. */
export function trafficTitle(pick: TrafficPick, ship: ShipRow | undefined, aircraft: AircraftRow | undefined): string {
  if (pick.kind === "ship") return ship ? t("traffic.card.ship_title", { name: shipName(ship) }) : "";
  return aircraft ? t("traffic.card.aircraft_title", { name: aircraftName(aircraft) }) : "";
}

export interface FeedLook {
  state: string;
  tone: string;
  line: string;
  /** behind the arrow: when it was read last, and whose data it is */
  updated: string;
  licence: string;
}

/** The status row of a feed under its switch: the state as a word in the colour of the radio's row, and one quiet line. */
export function feedLook(feed: "ais" | "adsb", state: FeedState): FeedLook {
  const source = SOURCES[feed];
  const behind = {
    updated: state.updated_at === null ? "" : t("settings.traffic.fold.updated", { time: hourMinuteText(state.updated_at) }),
    licence: t(`settings.traffic.fold.licence.${feed}`),
  };
  switch (state.state) {
    case "off":
      return { state: t("settings.tnc.state.stopped"), tone: "tnc-stopped", line: t("settings.traffic.line.off"), ...behind };
    case "waiting":
      return { state: t("settings.tnc.state.waiting"), tone: "tnc-waiting", line: t("settings.traffic.line.waiting"), ...behind };
    case "connecting":
      return { state: t("settings.tnc.state.connecting"), tone: "tnc-connecting", line: t("settings.traffic.line.connecting", { source }), ...behind };
    case "failing":
      return {
        state: t("settings.traffic.state.failing"),
        tone: "tnc-waiting",
        line: t("settings.traffic.line.failing", { source, why: state.problem }),
        ...behind,
      };
    default: {
      const values = { source, n: state.count, km: Math.round(state.radius_km) };
      const line = feed === "ais" ? t("settings.traffic.line.ships", values) : t("settings.traffic.line.aircraft", values);
      return { state: t("settings.traffic.state.receiving"), tone: "tnc-connected", line, ...behind };
    }
  }
}
