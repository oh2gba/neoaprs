// What the beacon status at the top of the Beacon tab says (components/BeaconStatus.vue), in the look of the radio status: a label, one coloured pill and plain lines. A fixed station says when the last beacon went and when the timer sends the next
// ("Last beacon 4 min ago · next in 56 min (every 60 min)"); a moving station says the GPS (the pill is the state of the GPS, the line the fix or why there is none) and, under it, what SmartBeaconing does (lib/gpsstatus.ts has those words).
// While the beacon is Off (the interval is 0), for either, the label is Beacon, the pill is off and the line says "Beacon off".
import { t } from "@/i18n";
import { dateTimeText, agoWords, untilText } from "@/lib/format";
import { beaconOff } from "@/lib/beaconoff";
import { gpsProblem, gpsStateText, gpsStatus, isMoving, mobileBeaconText } from "@/lib/gpsstatus";
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
  /** why there is no fix, when the line does not say it */
  problem: string;
}

/** Whether the timer will send a beacon: the interval is not 0 and the daemon has a time for the next. */
const timed = (status: StatusMessage): boolean => status.beacon_interval_min > 0 && status.beacon_next_due !== null;

/** The line of a fixed station: the last beacon and the timer, "Last beacon 4 min ago · next in 56 min (every 60 min)". */
function fixedLine(status: StatusMessage, nowMs: number): string {
  const ago = agoWords(status.beacon_last_sent, nowMs);
  const never = status.beacon_last_sent === null;
  if (!timed(status)) return never ? t("beacon.line.untimed_none") : t("beacon.line.untimed", { ago });
  const values = { when: untilText(status.beacon_next_due, nowMs), minutes: status.beacon_interval_min };
  return never ? t("beacon.line.timed_none", values) : t("beacon.line.timed", { ago, ...values });
}

/** The block for the status the daemon last told (`status`), the GPS topic (`gps`), the settings in force (`values`) and the time now. A station moves when the daemon says its beacon follows the GPS, before it has told when the settings say so. */
export function beaconBlock(status: StatusMessage | null, gps: GpsState | null, values: Readonly<Record<string, string>>, nowMs: number): BeaconBlock {
  const moving = gps === null ? isMoving(values) : gps.mobile;
  if (beaconOff(values)) {
    return {
      moving,
      label: t("beacon.label"),
      pill: { text: t("beacon.state.off"), tone: "beacon-off" },
      line: t("beacon.line.off"),
      hover: undefined,
      smart: null,
      problem: "",
    };
  }
  if (moving) {
    return {
      moving,
      label: t("gps.label"),
      pill: gps === null ? null : { text: gpsStateText(gps.state), tone: `gps-${gps.state}` },
      line: gps === null ? t("settings.no_word") : gpsStatus(gps, values, nowMs),
      hover: undefined,
      smart: mobileBeaconText(gps, nowMs),
      problem: gps === null ? "" : gpsProblem(gps),
    };
  }
  const on = status !== null && timed(status);
  return {
    moving,
    label: t("beacon.label"),
    pill: status === null ? null : { text: t(on ? "beacon.state.on" : "beacon.state.off"), tone: on ? "beacon-on" : "beacon-off" },
    line: status === null ? t("settings.no_word") : fixedLine(status, nowMs),
    hover: status === null || status.beacon_last_sent === null ? undefined : dateTimeText(status.beacon_last_sent),
    smart: null,
    problem: "",
  };
}
