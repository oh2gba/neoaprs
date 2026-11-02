// What the beacon status at the top of the My station tab says (components/BeaconStatus.vue), in the look of the radio status: a label, one coloured pill and plain lines. A fixed station says when the last beacon went and when the timer sends the next
// ("Last beacon 4 min ago · next in 56 min (every 60 min)"); a moving station says the GPS (the pill is the state of the GPS, the line the fix or why there is none) and, under it, what SmartBeaconing does (lib/gpsstatus.ts has those words).
// While the beacon is Off (the interval is 0) a fixed station has the label Beacon, the pill off and the line "no automatic beacon · Beacon now still sends"; a moving station keeps showing the GPS (the pill and the fix line, so that the fix can be watched) and says the same on the line under it, where SmartBeaconing's words would be.
// In RX only (nothing is sent) the pill is off in the warn colour and the line "RX only: nothing is sent", as the Digipeater's; a moving station keeps the GPS and says it under it.
import { t } from "@/i18n";
import { dateTimeText, agoWords, untilText } from "@/lib/format";
import { beaconOff } from "@/lib/beaconoff";
import { gpsProblem, gpsStateText, gpsStatus, isMoving, mobileBeaconText } from "@/lib/gpsstatus";
import { fmOn, hfOn } from "@/lib/radiosides";
import type { GpsState, StatusMessage } from "@/protocol/protocol";

export interface BeaconBlock {
  /** whether the station moves: the beacon follows a GPS */
  moving: boolean;
  /** "Beacon" for a fixed station, "GPS" for a moving one */
  label: string;
  /** the word on the pill and the class that colours it; null while the daemon has not told yet */
  pill: { text: string; tone: string } | null;
  /** the first line */
  line: string;
  /** the full time of the last beacon, on hover, for a fixed station that has sent one */
  hover: string | undefined;
  /** the SmartBeaconing line of a moving station */
  smart: string | null;
  /** one quiet line for each radio ("FM: last beacon 4 min ago · next in 26 min"), only while both radios are on: the row's line is the latest and the soonest of the two, these are the detail */
  radios: string[];
  /** why there is no fix, when the line does not say it */
  problem: string;
  /** set when the line is "RX only: nothing is sent", which leads to the setting */
  rxOnly?: true;
}

/** The earlier of two times of the wire, the later (null for none). A time that is not one is left out. */
function pick(times: readonly (string | null)[], later: boolean): string | null {
  const found = times.filter((time): time is string => time !== null && !Number.isNaN(Date.parse(time)));
  if (found.length === 0) return null;
  return found.reduce((best, time) => (Date.parse(time) > Date.parse(best) === later ? time : best));
}

/** The beacons the daemon told: the FM radio's (`beacon_*`) and the HF radio's (`hf_beacon_*`, null while HF is off). The row's line is the latest beacon on any radio and the next due on any radio. */
function times(status: StatusMessage): { last: string | null; next: string | null } {
  return {
    last: pick([status.beacon_last_sent, status.hf_beacon_last_sent], true),
    next: pick([status.beacon_next_due, status.hf_beacon_next_due], false),
  };
}

/** Whether the timer will send a beacon: the interval is not 0 and the daemon has a time for the next. */
const timed = (status: StatusMessage): boolean => status.beacon_interval_min > 0 && times(status).next !== null;

/** The line of a fixed station: the last beacon and the timer, "Last beacon 4 min ago · next in 56 min (every 60 min)". */
function fixedLine(status: StatusMessage, nowMs: number): string {
  const { last, next } = times(status);
  const ago = agoWords(last, nowMs);
  const never = last === null;
  if (!timed(status)) return never ? t("beacon.line.untimed_none") : t("beacon.line.untimed", { ago });
  const values = { when: untilText(next, nowMs), minutes: status.beacon_interval_min };
  return never ? t("beacon.line.timed_none", values) : t("beacon.line.timed", { ago, ...values });
}

/** The line of one radio's beacon, without the interval: "last beacon 4 min ago · next in 26 min". */
function radioLine(last: string | null, next: string | null, interval: number, nowMs: number): string {
  const ago = agoWords(last, nowMs);
  if (interval > 0 && next !== null) {
    const when = untilText(next, nowMs);
    return last === null ? t("beacon.fold.timed_none", { when }) : t("beacon.fold.timed", { ago, when });
  }
  return last === null ? t("beacon.fold.untimed_none") : t("beacon.fold.untimed", { ago });
}

/** The lines behind the arrow while both radios are on: FM's beacon and HF's. */
function radioLines(status: StatusMessage, values: Readonly<Record<string, string>>, nowMs: number): string[] {
  if (!(fmOn(values) && hfOn(values))) return [];
  const interval = status.beacon_interval_min;
  return [
    t("beacon.fold.fm", { line: radioLine(status.beacon_last_sent, status.beacon_next_due, interval, nowMs) }),
    t("beacon.fold.hf", { line: radioLine(status.hf_beacon_last_sent, status.hf_beacon_next_due, interval, nowMs) }),
  ];
}

/** The block of a moving station: the GPS, and under it SmartBeaconing's words, or why nothing is sent (`quiet`, empty when something is). */
function movingBlock(gps: GpsState | null, values: Readonly<Record<string, string>>, nowMs: number, quiet: string): BeaconBlock {
  return {
    moving: true,
    label: t("gps.label"),
    pill: gps === null ? null : { text: gpsStateText(gps.state), tone: `gps-${gps.state}` },
    line: gps === null ? t("settings.no_word") : gpsStatus(gps, values, nowMs),
    hover: undefined,
    radios: [],
    smart: quiet || mobileBeaconText(gps, nowMs),
    problem: gps === null ? "" : gpsProblem(gps),
  };
}

/** The block of a fixed station whose beacon is not Off: on or off by the timer, the line of the latest and the next beacon, the full time of the latest on hover, and a line for each radio while both are on. */
function fixedBlock(status: StatusMessage | null, values: Readonly<Record<string, string>>, nowMs: number): BeaconBlock {
  const base = { moving: false, label: t("beacon.label"), smart: null, problem: "" };
  if (status === null) return { ...base, pill: null, line: t("settings.no_word"), hover: undefined, radios: [] };
  const on = timed(status);
  const { last } = times(status);
  return {
    ...base,
    pill: { text: t(on ? "beacon.state.on" : "beacon.state.off"), tone: on ? "beacon-on" : "beacon-off" },
    line: fixedLine(status, nowMs),
    hover: last === null ? undefined : dateTimeText(last),
    radios: radioLines(status, values, nowMs),
  };
}

/** The block for the status the daemon last told (`status`), the GPS topic (`gps`), the settings in force (`values`) and the time now. A station moves when the daemon says its beacon follows the GPS, before it has told when the settings say so. */
export function beaconBlock(status: StatusMessage | null, gps: GpsState | null, values: Readonly<Record<string, string>>, nowMs: number): BeaconBlock {
  const moving = gps === null ? isMoving(values) : gps.mobile;
  const rxOnly = values["station/transmit"] === "false";
  const quiet = rxOnly ? t("beacon.line.rx_only") : beaconOff(values) ? t("beacon.line.off") : "";
  if (moving) return movingBlock(gps, values, nowMs, quiet);
  if (quiet) {
    return {
      moving,
      label: t("beacon.label"),
      pill: { text: t("beacon.state.off"), tone: rxOnly ? "tnc-waiting" : "beacon-off" },
      line: quiet,
      hover: undefined,
      radios: [],
      smart: null,
      problem: "",
      ...(rxOnly ? { rxOnly: true as const } : {}),
    };
  }
  return fixedBlock(status, values, nowMs);
}
