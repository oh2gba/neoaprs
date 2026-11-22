// The details of a position or station that the daemon decodes beyond where it is: data extensions
// (PHG, range, DF, area), the Maidenhead locator, telemetry channels, the voice frequency with its
// tone, offset and range, the storm data of a hurricane object, and the time a packet carries
// (which may be the sender's local time).
import { formatNumber, t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import { bearingTitle, dateTimeText, pad2, positionText } from "@/lib/format";
import { distanceWithUnit, heightText, rangeText, speedText, stormPressureText } from "@/lib/units";
import type {
  AreaValues,
  DecodedObject,
  DecodedOther,
  DecodedPosition,
  DecodedStatus,
  ExtensionValues,
  FrequencyValues,
  LocatorValues,
  PacketRow,
  StormValues,
  TelemetryValues,
} from "@/protocol/protocol";

/** Where an antenna favours, drawn as an arrow (a circle for omni); `title` says it in words. */
interface Directivity {
  deg: number | null;
  title: string;
}

interface DetailRow {
  label: string;
  text: string;
  /** The antenna's direction, drawn after the text; none for a row with no antenna. */
  direction?: Directivity;
}

const directivity = (deg: number | null): Directivity => ({
  deg,
  title: deg === null ? t("station.ext.omni") : bearingTitle(deg),
});

/** One row for each data extension a position had: "PHG", "Range", "DF signal", "DF bearing",
 * "Area". */
export function extensionRows(ext: ExtensionValues | null): DetailRow[] {
  if (ext === null) return [];
  const rows: DetailRow[] = [];
  if (ext.phg !== null) {
    const p = ext.phg;
    rows.push({
      label: "PHG",
      text: t("station.ext.phg_value", {
        power: p.power_w,
        height: heightText(p.height_m),
        gain: p.gain_db,
        range: rangeText(p.range_km),
      }),
      direction: directivity(p.direction_deg),
    });
  }
  if (ext.range_km !== null) rows.push({ label: t("station.ext.range"), text: rangeText(ext.range_km) });
  if (ext.dfs !== null) {
    const d = ext.dfs;
    rows.push({
      label: t("station.ext.df_signal"),
      text: t("station.ext.dfs_value", { strength: d.strength, height: heightText(d.height_m), gain: d.gain_db }),
      direction: directivity(d.direction_deg),
    });
  }
  if (ext.df_bearing !== null) {
    const b = ext.df_bearing;
    rows.push({
      label: t("station.ext.df_bearing"),
      text: t("station.ext.df_bearing_value", {
        bearing: b.bearing_deg,
        range: rangeText(b.range_km),
        quality: b.quality,
        hits: b.hits,
      }),
    });
  }
  if (ext.area !== null) {
    const a = ext.area;
    rows.push({
      label: t("station.ext.area"),
      text:
        a.lon_offset_deg < 0
          ? t("station.ext.area_value_left", { ...areaWords(a), down: a.lat_offset_deg, left: -a.lon_offset_deg })
          : t("station.ext.area_value", { ...areaWords(a), down: a.lat_offset_deg, right: a.lon_offset_deg }),
    });
  }
  return rows;
}

/** The shapes and colours of an area object in the page's words: the daemon names each by the
 * specification's word (`AreaValues`), which the catalogue has an id for. */
const SHAPE_WORDS: Record<AreaValues["shape"], MessageId> = {
  "open circle": "station.area.shape.open_circle",
  line: "station.area.shape.line",
  "open ellipse": "station.area.shape.open_ellipse",
  "open triangle": "station.area.shape.open_triangle",
  "open box": "station.area.shape.open_box",
  "filled circle": "station.area.shape.filled_circle",
  "line down-left": "station.area.shape.line_down_left",
  "filled ellipse": "station.area.shape.filled_ellipse",
  "filled triangle": "station.area.shape.filled_triangle",
  "filled box": "station.area.shape.filled_box",
};
const COLOUR_WORDS: Record<AreaValues["colour"], MessageId> = {
  black: "station.area.colour.black",
  blue: "station.area.colour.blue",
  green: "station.area.colour.green",
  cyan: "station.area.colour.cyan",
  red: "station.area.colour.red",
  violet: "station.area.colour.violet",
  yellow: "station.area.colour.yellow",
  gray: "station.area.colour.gray",
  "dim black": "station.area.colour.dim_black",
  "dim blue": "station.area.colour.dim_blue",
  "dim green": "station.area.colour.dim_green",
  "dim cyan": "station.area.colour.dim_cyan",
  "dim red": "station.area.colour.dim_red",
  "dim violet": "station.area.colour.dim_violet",
  "dim yellow": "station.area.colour.dim_yellow",
  "dim gray": "station.area.colour.dim_gray",
  unknown: "station.area.colour.unknown",
};

/** The shape and colour of an area object, as the values of `station.ext.area_value`; a word the
 * page does not know is shown as an area and an unknown colour. */
export function areaWords(area: Pick<AreaValues, "shape" | "colour">): { shape: string; colour: string } {
  const shape = SHAPE_WORDS[area.shape] as MessageId | undefined;
  const colour = COLOUR_WORDS[area.colour] as MessageId | undefined;
  return { shape: t(shape ?? "station.ext.area"), colour: t(colour ?? "station.area.colour.unknown") };
}

/** "IO91sx, 51.97917 N 0.45833 W": the grid square and its centre; a dash for none. */
export function locatorText(loc: LocatorValues | null): string {
  return loc === null ? "-" : `${loc.grid}, ${positionText(loc.lat, loc.lon)}`;
}

/** A value to at most two decimals: 10.35, 5, 0.5. */
function valueText(v: number): string {
  return String(Math.round(v * 100) / 100);
}

/** "#5: Battery 10.35 V, Temp 24 deg.F": the analog channels with the names and units the station
 * defined (or A1 to A5). */
export function telemetryText(telemetry: TelemetryValues | null): string {
  if (telemetry === null) return "-";
  const channels = telemetry.channels
    .map((c) => `${c.name} ${valueText(c.value)}${c.unit === "" ? "" : ` ${c.unit}`}`)
    .join(", ");
  return telemetry.sequence === null
    ? channels
    : t("station.telemetry.numbered", { number: telemetry.sequence, channels });
}

/** "Camera on, Chute off": the digital channels, named as the station defined them (or B1 to B8).
 */
export function telemetryBitsText(telemetry: TelemetryValues | null): string {
  return telemetry === null
    ? "-"
    : telemetry.bits.map((b) => t("station.telemetry.bit", { name: b.name, state: b.on ? "on" : "off" })).join(", ");
}

/** The offset with its sign: "-600 kHz", "+1000 kHz". */
function offsetText(khz: number): string {
  return t("station.freq.offset", { khz: khz > 0 ? `+${khz}` : String(khz) });
}

/** A voice frequency with the fields it was sent with: "145.775 MHz, tone 118 Hz, -600 kHz, range
 * 40 km"; only what the sender said. */
export function frequencyText(f: FrequencyValues): string {
  const parts = [t("station.freq.mhz", { mhz: formatNumber(f.mhz, 3) })];
  if (f.tone_hz !== null)
    parts.push(t(f.tone_both ? "station.freq.tone_both" : "station.freq.tone", { hz: f.tone_hz }));
  if (f.dcs !== null) parts.push(t("station.freq.dcs", { code: f.dcs }));
  if (f.tone_off) parts.push(t("station.freq.no_tone"));
  if (f.tone_burst) parts.push(t("station.freq.burst"));
  if (f.narrow) parts.push(t("station.freq.narrow"));
  if (f.offset_khz !== null) parts.push(f.offset_khz === 0 ? t("station.freq.simplex") : offsetText(f.offset_khz));
  if (f.range_km !== null) parts.push(t("station.freq.range", { distance: distanceWithUnit(f.range_km) }));
  if (f.rx_mhz !== null) parts.push(t("station.freq.receive", { mhz: formatNumber(f.rx_mhz, 3) }));
  return parts.join(", ");
}

/** The storm data in words: "Hurricane, wind 278 km/h, gusts 370 km/h, pressure 980 hPa, ..."; only
 * the fields the report had. */
export function stormText(s: StormValues): string {
  const parts = [t("station.storm.kind", { kind: s.storm_type })];
  if (s.wind_kmh !== null) parts.push(t("station.storm.wind", { speed: speedText(s.wind_kmh) }));
  if (s.gust_kmh !== null) parts.push(t("station.storm.gusts", { speed: speedText(s.gust_kmh) }));
  if (s.pressure_hpa !== null) parts.push(t("station.storm.pressure", { value: stormPressureText(s.pressure_hpa) }));
  if (s.hurricane_radius_km !== null)
    parts.push(t("station.storm.hurricane_radius", { distance: distanceWithUnit(s.hurricane_radius_km) }));
  if (s.storm_radius_km !== null)
    parts.push(t("station.storm.storm_radius", { distance: distanceWithUnit(s.storm_radius_km) }));
  if (s.gale_radius_km !== null)
    parts.push(t("station.storm.gale_radius", { distance: distanceWithUnit(s.gale_radius_km) }));
  return parts.join(", ");
}

type Timed = DecodedPosition | DecodedObject | DecodedStatus | DecodedOther;

/** The time a packet carries, and whether it was sent as local time (`/`): then it is shown as
 * sent, not converted to ours. */
function carried(row: PacketRow): { at: string; local: boolean } | null {
  const d = row.decoded as Timed | { type: string };
  if (d.type === "object") {
    const o = d as DecodedObject;
    return o.timestamp === null ? null : { at: o.timestamp, local: o.position.timestamp_local };
  }
  if (d.type === "position" || d.type === "status" || d.type === "other") {
    const stamped = d as DecodedPosition | DecodedStatus | DecodedOther;
    return stamped.timestamp === null
      ? null
      : { at: stamped.timestamp, local: "timestamp_local" in stamped && stamped.timestamp_local };
  }
  return null;
}

/** The time the packet itself carries, for its detail: "2026-10-21 14:03:12" in our time, or "09
 * 23:45 local" for a sender's local time; null if none. */
export function sentTimeText(row: PacketRow): string | null {
  const sent = carried(row);
  if (sent === null) return null;
  if (!sent.local) return dateTimeText(sent.at);
  const d = new Date(sent.at);
  return t("station.sent_local", {
    time: `${pad2(d.getUTCDate())} ${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}`,
  });
}
