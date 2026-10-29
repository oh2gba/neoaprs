// The details of a position or a station that the daemon decodes beyond where it is: the data extensions (PHG, range, DF, area), the Maidenhead locator, the telemetry channels, the voice frequency with its
// tone, offset and range, the storm data of a hurricane object, and the time a packet carries (which may be the sender's local time).
import { formatNumber, t } from "@/i18n";
import { bearingTitle, dateTimeText, distanceText, pad2, positionText, speedText } from "@/lib/format";
import type {
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

/** Where an antenna favours, to be drawn as an arrow (a circle for omni); `title` says it in words, the compass point and the degrees. */
interface Directivity {
  deg: number | null;
  title: string;
}

interface DetailRow {
  label: string;
  text: string;
  /** The antenna's direction, drawn after the text; none for a row that has no antenna. */
  direction?: Directivity;
}

const directivity = (deg: number | null): Directivity => ({ deg, title: deg === null ? t("station.ext.omni") : bearingTitle(deg) });

/** One row for each data extension a position had: "PHG", "Range", "DF signal", "DF bearing", "Area". */
export function extensionRows(ext: ExtensionValues | null): DetailRow[] {
  if (ext === null) return [];
  const rows: DetailRow[] = [];
  if (ext.phg !== null) {
    const p = ext.phg;
    rows.push({
      label: "PHG",
      text: t("station.ext.phg_value", {
        power: p.power_w,
        height: Math.round(p.height_m),
        gain: p.gain_db,
        range: Math.round(p.range_km),
      }),
      direction: directivity(p.direction_deg),
    });
  }
  if (ext.range_km !== null) rows.push({ label: t("station.ext.range"), text: `${Math.round(ext.range_km)} km` });
  if (ext.dfs !== null) {
    const d = ext.dfs;
    rows.push({
      label: t("station.ext.df_signal"),
      text: t("station.ext.dfs_value", { strength: d.strength, height: Math.round(d.height_m), gain: d.gain_db }),
      direction: directivity(d.direction_deg),
    });
  }
  if (ext.df_bearing !== null) {
    const b = ext.df_bearing;
    rows.push({
      label: t("station.ext.df_bearing"),
      text: t("station.ext.df_bearing_value", { bearing: b.bearing_deg, range: Math.round(b.range_km), quality: b.quality, hits: b.hits }),
    });
  }
  if (ext.area !== null) {
    const a = ext.area;
    rows.push({
      label: t("station.ext.area"),
      text:
        a.lon_offset_deg < 0
          ? t("station.ext.area_value_left", { colour: a.colour, shape: a.shape, down: a.lat_offset_deg, left: -a.lon_offset_deg })
          : t("station.ext.area_value", { colour: a.colour, shape: a.shape, down: a.lat_offset_deg, right: a.lon_offset_deg }),
    });
  }
  return rows;
}

/** "IO91sx, 51.97917 N 0.45833 W": the grid square and the centre of it; a dash for none. */
export function locatorText(loc: LocatorValues | null): string {
  return loc === null ? "-" : `${loc.grid}, ${positionText(loc.lat, loc.lon)}`;
}

/** A value to at most two decimals: 10.35, 5, 0.5. */
function valueText(v: number): string {
  return String(Math.round(v * 100) / 100);
}

/** "#5: Battery 10.35 V, Temp 24 deg.F": the analog channels with the names and units the station defined (or A1 to A5). */
export function telemetryText(telemetry: TelemetryValues | null): string {
  if (telemetry === null) return "-";
  const channels = telemetry.channels.map((c) => `${c.name} ${valueText(c.value)}${c.unit === "" ? "" : ` ${c.unit}`}`).join(", ");
  return telemetry.sequence === null ? channels : t("station.telemetry.numbered", { number: telemetry.sequence, channels });
}

/** "Camera on, Chute off": the digital channels, named as the station defined them (or B1 to B8). */
export function telemetryBitsText(telemetry: TelemetryValues | null): string {
  return telemetry === null ? "-" : telemetry.bits.map((b) => t("station.telemetry.bit", { name: b.name, state: b.on ? "on" : "off" })).join(", ");
}

/** The offset with its sign: "-600 kHz", "+1000 kHz". */
function offsetText(khz: number): string {
  return t("station.freq.offset", { khz: khz > 0 ? `+${khz}` : String(khz) });
}

/** A voice frequency with the fields it was sent with: "145.775 MHz, tone 118 Hz, -600 kHz, range 40 km"; only what the sender said. */
export function frequencyText(f: FrequencyValues): string {
  const parts = [t("station.freq.mhz", { mhz: formatNumber(f.mhz, 3) })];
  if (f.tone_hz !== null) parts.push(t(f.tone_both ? "station.freq.tone_both" : "station.freq.tone", { hz: f.tone_hz }));
  if (f.dcs !== null) parts.push(t("station.freq.dcs", { code: f.dcs }));
  if (f.tone_off) parts.push(t("station.freq.no_tone"));
  if (f.tone_burst) parts.push(t("station.freq.burst"));
  if (f.narrow) parts.push(t("station.freq.narrow"));
  if (f.offset_khz !== null) parts.push(f.offset_khz === 0 ? t("station.freq.simplex") : offsetText(f.offset_khz));
  if (f.range_km !== null) parts.push(t("station.freq.range", { km: distanceText(f.range_km) }));
  if (f.rx_mhz !== null) parts.push(t("station.freq.receive", { mhz: formatNumber(f.rx_mhz, 3) }));
  return parts.join(", ");
}

/** The storm data in words: "Hurricane, wind 278 km/h, gusts 370 km/h, pressure 980 hPa, hurricane winds out to 167 km, ..."; only the fields the report had. */
export function stormText(s: StormValues): string {
  const parts = [t("station.storm.kind", { kind: s.storm_type })];
  if (s.wind_kmh !== null) parts.push(t("station.storm.wind", { speed: speedText(s.wind_kmh) }));
  if (s.gust_kmh !== null) parts.push(t("station.storm.gusts", { speed: speedText(s.gust_kmh) }));
  if (s.pressure_hpa !== null) parts.push(t("station.storm.pressure", { value: `${s.pressure_hpa} hPa` }));
  if (s.hurricane_radius_km !== null) parts.push(t("station.storm.hurricane_radius", { km: distanceText(s.hurricane_radius_km) }));
  if (s.storm_radius_km !== null) parts.push(t("station.storm.storm_radius", { km: distanceText(s.storm_radius_km) }));
  if (s.gale_radius_km !== null) parts.push(t("station.storm.gale_radius", { km: distanceText(s.gale_radius_km) }));
  return parts.join(", ");
}

type Timed = DecodedPosition | DecodedObject | DecodedStatus | DecodedOther;

/** The time a packet carries and whether it was sent as local time (`/`): then it is shown as sent, in the sender's clock, not converted to ours. */
function carried(row: PacketRow): { at: string; local: boolean } | null {
  const d = row.decoded as Timed | { type: string };
  if (d.type === "object") {
    const o = d as DecodedObject;
    return o.timestamp === null ? null : { at: o.timestamp, local: o.position.timestamp_local };
  }
  if (d.type === "position" || d.type === "status" || d.type === "other") {
    const stamped = d as DecodedPosition | DecodedStatus | DecodedOther;
    return stamped.timestamp === null ? null : { at: stamped.timestamp, local: "timestamp_local" in stamped && stamped.timestamp_local };
  }
  return null;
}

/** The time that the packet itself carries, for its detail: "2026-10-21 14:03:12" in our time, or "09 23:45 local" for a time the sender gave in its local time; null when it carries none. */
export function sentTimeText(row: PacketRow): string | null {
  const sent = carried(row);
  if (sent === null) return null;
  if (!sent.local) return dateTimeText(sent.at);
  const d = new Date(sent.at);
  return t("station.sent_local", { time: `${pad2(d.getUTCDate())} ${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}` });
}
