// The details of a position or a station that the daemon decodes beyond where it is: the data extensions (PHG, range, DF, area), the Maidenhead locator, the telemetry channels, and the time a packet
// carries (which may be the sender's local time).
import { dateTimeText, positionText } from "@/lib/format";
import type {
  DecodedObject,
  DecodedOther,
  DecodedPosition,
  DecodedStatus,
  ExtensionValues,
  LocatorValues,
  PacketRow,
  TelemetryValues,
} from "@/protocol/protocol";

interface DetailRow {
  label: string;
  text: string;
}

const directionText = (deg: number | null): string => (deg === null ? "omni" : `${deg}°`);

/** One row for each data extension a position had: "PHG", "Range", "DF signal", "DF bearing", "Area". */
export function extensionRows(ext: ExtensionValues | null): DetailRow[] {
  if (ext === null) return [];
  const rows: DetailRow[] = [];
  if (ext.phg !== null) {
    const p = ext.phg;
    rows.push({
      label: "PHG",
      text: `${p.power_w} W, ${Math.round(p.height_m)} m, ${p.gain_db} dB, ${directionText(p.direction_deg)}, range ${Math.round(p.range_km)} km`,
    });
  }
  if (ext.range_km !== null) rows.push({ label: "Range", text: `${Math.round(ext.range_km)} km` });
  if (ext.dfs !== null) {
    const d = ext.dfs;
    rows.push({ label: "DF signal", text: `S${d.strength}, ${Math.round(d.height_m)} m, ${d.gain_db} dB, ${directionText(d.direction_deg)}` });
  }
  if (ext.df_bearing !== null) {
    const b = ext.df_bearing;
    rows.push({ label: "DF bearing", text: `${b.bearing_deg}°, range ${Math.round(b.range_km)} km, quality ${b.quality}, hits ${b.hits}` });
  }
  if (ext.area !== null) {
    const a = ext.area;
    rows.push({ label: "Area", text: `${a.colour} ${a.shape}, ${a.lat_offset_deg}° down, ${a.lon_offset_deg}° right` });
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
export function telemetryText(t: TelemetryValues | null): string {
  if (t === null) return "-";
  const channels = t.channels.map((c) => `${c.name} ${valueText(c.value)}${c.unit === "" ? "" : ` ${c.unit}`}`).join(", ");
  return `${t.sequence === null ? "" : `#${t.sequence}: `}${channels}`;
}

/** "Camera on, Chute off": the digital channels, named as the station defined them (or B1 to B8). */
export function telemetryBitsText(t: TelemetryValues | null): string {
  return t === null ? "-" : t.bits.map((b) => `${b.name} ${b.on ? "on" : "off"}`).join(", ");
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
    const t = d as DecodedPosition | DecodedStatus | DecodedOther;
    return t.timestamp === null ? null : { at: t.timestamp, local: "timestamp_local" in t && t.timestamp_local };
  }
  return null;
}

/** The time that the packet itself carries, for its detail: "2026-10-21 14:03:12" in our time, or "09 23:45 local" for a time the sender gave in its local time; null when it carries none. */
export function sentTimeText(row: PacketRow): string | null {
  const t = carried(row);
  if (t === null) return null;
  if (!t.local) return dateTimeText(t.at);
  const d = new Date(t.at);
  const pad = (n: number): string => String(n).padStart(2, "0");
  return `${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} local`;
}
