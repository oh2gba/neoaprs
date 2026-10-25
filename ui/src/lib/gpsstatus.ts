// What the beacon status of a moving station says in plain words (lib/beaconstatus.ts, components/BeaconStatus.vue), as the radio status does for the TNC (lib/tncstatus.ts): a word for the state on a pill, one line with the fix or why there
// is none, and the line that says when SmartBeaconing sends next. The fix is told by the daemon (the topic `gps`); the address or the port that is being connected to is a setting.
import { formatNumber, t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import { NONE, ageText, altitudeText, speedText, untilText } from "@/lib/format";
import type { GpsState } from "@/protocol/protocol";

const STATES: Record<GpsState["state"], MessageId> = {
  off: "gps.state.off",
  connecting: "gps.state.connecting",
  no_fix: "gps.state.no_fix",
  fix: "gps.state.fix",
  stale: "gps.state.stale",
};

/** Whether the station moves: its position is a GPS's (`gps/source` is gpsd or serial) and the beacon follows it; else it is a fixed station at the home position. `values` are the settings, key to text. */
export function isMoving(values: Readonly<Record<string, string>>): boolean {
  const source = values["gps/source"];
  return source === "gpsd" || source === "serial";
}

/** The word on the pill for the state of the GPS. */
export const gpsStateText = (state: GpsState["state"]): string => t(STATES[state]);

const REASONS: Record<Exclude<GpsState["last_beacon_reason"], "">, MessageId> = {
  start: "gps.reason.start",
  time: "gps.reason.time",
  turn: "gps.reason.turn",
  request: "gps.reason.request",
};

/** Degrees with N or S, E or W, to four decimals (11 m), the way the line of a fix writes a place: "60.4295 N 24.1452 E". */
function placeText(lat: number, lon: number): string {
  return `${formatNumber(Math.abs(lat), 4)} ${lat < 0 ? "S" : "N"} ${formatNumber(Math.abs(lon), 4)} ${lon < 0 ? "W" : "E"}`;
}

/** What the fix says besides where it is: the speed, the course, the altitude and the satellites, each only when the receiver gave it. */
function facts(gps: GpsState): string[] {
  return [
    ...(gps.speed_kmh === null ? [] : [speedText(gps.speed_kmh)]),
    ...(gps.course_deg === null ? [] : [t("gps.course", { deg: Math.round(gps.course_deg) % 360 })]),
    ...(gps.altitude_m === null ? [] : [altitudeText(gps.altitude_m)]),
    ...(gps.satellites === null ? [] : [t("gps.satellites", { n: gps.satellites })]),
  ];
}

/** The line that connecting is told in: what is being connected to, from the settings (`values`, key to text). */
function connectingText(gps: GpsState, values: Readonly<Record<string, string>>): string {
  const host = (values["gps/host"] ?? "").trim();
  const device = (values["gps/device"] ?? "").trim();
  if (gps.source === "gpsd" && host !== "") return t("gps.connecting_gpsd", { host });
  if (gps.source === "serial" && device !== "") return t("gps.connecting_serial", { device, baud: values["gps/baud"] ?? "" });
  return t("gps.connecting");
}

/** The GPS line of the beacon status: "Off", "Connecting to gpsd at 127.0.0.1:2947", "No fix yet", "Fix: 60.4295 N 24.1452 E, 48 km/h, course 215°, 103 m, 9 satellites, 2 s ago" or "Fix lost 3 min ago". */
export function gpsStatus(gps: GpsState, values: Readonly<Record<string, string>>, nowMs: number): string {
  if (gps.state === "off") return t("gps.off");
  if (gps.state === "connecting") return connectingText(gps, values);
  if (gps.state === "stale" && gps.fix_at !== null) return t("gps.stale", { span: ageText(gps.fix_at, nowMs) });
  if (gps.state !== "fix" || gps.lat === null || gps.lon === null) return t("gps.no_fix");
  const age = gps.fix_at === null ? [] : [t("time.ago", { span: ageText(gps.fix_at, nowMs) })];
  return t("gps.fix", { facts: [placeText(gps.lat, gps.lon), ...facts(gps), ...age].join(t("gps.separator")) });
}

/** The daemon's reason there is no fix (its own line, in English: "Connection refused"), when the status line does not already say it; "" for a fix and for an old fix, which the line states. */
export function gpsProblem(gps: GpsState): string {
  return gps.problem !== "" && gps.state !== "fix" && gps.state !== "stale" ? gps.problem : "";
}

/** The reason the last beacon of a moving station went out, in words: "first fix", "time", "turn", "Beacon now". */
export function reasonText(reason: GpsState["last_beacon_reason"]): string {
  return reason === "" ? NONE : t(REASONS[reason]);
}

/** The SmartBeaconing line of the beacon status of a moving station: that nothing is sent without a fix, or when SmartBeaconing sends the next timed beacon and what the last one went for ("SmartBeaconing: next timed beacon in 42 s, last
 * sent 12 s ago (turn)"); null for a fixed station (the daemon says the beacon follows the GPS in `mobile`). */
export function mobileBeaconText(gps: GpsState | null, nowMs: number): string | null {
  if (gps === null || !gps.mobile) return null;
  if (gps.state !== "fix") return t("gps.beacon.no_fix");
  const last = gps.last_beacon_at !== null && gps.last_beacon_reason !== "";
  if (gps.next_beacon_at === null && !last) return t("gps.beacon.first");
  const span = last ? ageText(gps.last_beacon_at, nowMs) : "";
  const reason = reasonText(gps.last_beacon_reason);
  if (gps.next_beacon_at === null) return t("gps.beacon.last", { span, reason });
  const when = untilText(gps.next_beacon_at, nowMs);
  return last ? t("gps.beacon.next_last", { when, span, reason }) : t("gps.beacon.next", { when });
}

/** Whether a fix is there to follow: the receiver has one that is fresh. */
export function hasFix(gps: GpsState | null): gps is GpsState & { lat: number; lon: number } {
  return gps !== null && gps.state === "fix" && gps.lat !== null && gps.lon !== null;
}
