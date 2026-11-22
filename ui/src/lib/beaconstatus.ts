// The beacon status at the top of the My station tab (components/BeaconStatus.vue): a label, one
// coloured pill and plain lines.
// A fixed station shows when the last beacon went and when the timer sends the next. A moving
// station shows the GPS (pill: GPS state, line: the fix or why there is none) and, under it, what
// SmartBeaconing does (words in lib/gpsstatus.ts).
// With the beacon Off (interval 0) a fixed station shows the pill off and "no automatic beacon";
// a moving station keeps showing the GPS. In RX only the pill is off in the warn colour.
// With several radios on, a line per radio shows its own interval. The end of the file serves the
// Beacon group's radios (BeaconPane.vue, SettingsPath.vue): Send on ticks and Path rows. The Send
// on ticks of status, ask and local info are the same per-radio fields, read through
// `sendOnRadios`.
import { t } from "@/i18n";
import { dateTimeText, agoWords, untilText } from "@/lib/format";
import { beaconOff } from "@/lib/beaconoff";
import { gpsProblem, gpsStateText, gpsStatus, isMoving, mobileBeaconText } from "@/lib/gpsstatus";
import type { PageRadio, RadioId } from "@/lib/radios";
import type { ConfigValues, GpsState, RadioBeaconState, StatusMessage } from "@/protocol/protocol";

/**
 * A radio the beacon goes out on, as its line shows it. `smart`: the beacon follows the GPS, not an
 * interval.
 */
export interface BeaconRadio {
  name: string;
  beacon: RadioBeaconState;
  smart: boolean;
}

export interface BeaconBlock {
  /** whether the station moves: the beacon follows a GPS */
  moving: boolean;
  /** "Beacon" for a fixed station, "GPS" for a moving one */
  label: string;
  /** the pill's text and tone class; null until the daemon has reported */
  pill: { text: string; tone: string } | null;
  /** the first line */
  line: string;
  /** the full time of the last beacon (hover), for a fixed station that has sent one */
  hover: string | undefined;
  /** the SmartBeaconing line of a moving station */
  smart: string | null;
  /** a line per radio the beacon goes out on, only while several radios are on */
  radios: string[];
  /** why there is no fix, when the line does not say it */
  problem: string;
  /** set when the line is "RX only: nothing is sent"; it links to the setting */
  rxOnly?: true;
}

/**
 * The latest (`later`) or earliest of the given wire times; times that do not parse are ignored.
 */
function pick(times: readonly (string | null)[], later: boolean): string | null {
  const found = times.filter((time): time is string => time !== null && !Number.isNaN(Date.parse(time)));
  if (found.length === 0) return null;
  return found.reduce((best, time) => (Date.parse(time) > Date.parse(best) === later ? time : best));
}

/**
 * The last and next beacon times. With several radios on they come from the radios' own timers,
 * else from the status (the latest on any radio and the next due on any).
 */
function times(status: StatusMessage, radios: readonly BeaconRadio[]): { last: string | null; next: string | null } {
  if (radios.length > 0)
    return {
      last: pick(
        radios.map((radio) => radio.beacon.last_sent),
        true,
      ),
      next: pick(
        radios.map((radio) => radio.beacon.next_due),
        false,
      ),
    };
  return {
    last: pick([status.beacon_last_sent], true),
    next: pick([status.beacon_next_due], false),
  };
}

/** Whether the timer will send a beacon: the interval is not 0 and a next time is known. */
const timed = (status: StatusMessage, radios: readonly BeaconRadio[]): boolean => status.beacon_interval_min > 0 && times(status, radios).next !== null;

/**
 * The line of a fixed station: last beacon and timer (the interval is the shortest of the radios).
 */
function fixedLine(status: StatusMessage, radios: readonly BeaconRadio[], nowMs: number): string {
  const { last, next } = times(status, radios);
  const ago = agoWords(last, nowMs);
  const never = last === null;
  if (!timed(status, radios)) return never ? t("beacon.line.untimed_none") : t("beacon.line.untimed", { ago });
  const values = { when: untilText(next, nowMs), minutes: status.beacon_interval_min };
  return never ? t("beacon.line.timed_none", values) : t("beacon.line.timed", { ago, ...values });
}

/**
 * The line of one radio's beacon with its interval. A `smart` radio (SmartBeaconing) has no
 * interval; its next time is the one SmartBeaconing gives.
 */
function radioLine(beacon: RadioBeaconState, nowMs: number, smart: boolean): string {
  const { last_sent: last, next_due: next, interval_min: minutes } = beacon;
  const ago = agoWords(last, nowMs);
  if (minutes > 0 && next !== null) {
    const when = untilText(next, nowMs);
    if (smart) return last === null ? t("beacon.fold.timed_none", { when }) : t("beacon.fold.timed", { ago, when });
    return last === null ? t("beacon.fold.timed_none_every", { when, minutes }) : t("beacon.fold.timed_every", { ago, when, minutes });
  }
  return last === null ? t("beacon.fold.untimed_none") : t("beacon.fold.untimed", { ago });
}

/** The per-radio lines; with `moving`, radios with SmartBeaconing follow the GPS. */
const radioLines = (radios: readonly BeaconRadio[], nowMs: number, moving = false): string[] =>
  radios.map((radio) => t("radio.line", { name: radio.name, line: radioLine(radio.beacon, nowMs, moving && radio.smart) }));

/**
 * The block of a moving station: the GPS, then SmartBeaconing's words or `quiet` (why nothing is
 * sent). A radio without SmartBeaconing sends the timed beacon with the latest fix.
 */
function movingBlock(
  gps: GpsState | null,
  values: Readonly<Record<string, string>>,
  nowMs: number,
  quiet: string,
  radios: readonly BeaconRadio[],
): BeaconBlock {
  return {
    moving: true,
    label: t("gps.label"),
    pill: gps === null ? null : { text: gpsStateText(gps.state), tone: `gps-${gps.state}` },
    line: gps === null ? t("settings.no_word") : gpsStatus(gps, values, nowMs),
    hover: undefined,
    radios: quiet ? [] : radioLines(radios, nowMs, true),
    smart: quiet || mobileBeaconText(gps, nowMs),
    problem: gps === null ? "" : gpsProblem(gps),
  };
}

/** The block of a fixed station whose beacon is not Off. */
function fixedBlock(status: StatusMessage | null, radios: readonly BeaconRadio[], nowMs: number): BeaconBlock {
  const base = { moving: false, label: t("beacon.label"), smart: null, problem: "" };
  if (status === null) return { ...base, pill: null, line: t("settings.no_word"), hover: undefined, radios: [] };
  const on = timed(status, radios);
  const { last } = times(status, radios);
  return {
    ...base,
    pill: { text: t(on ? "beacon.state.on" : "beacon.state.off"), tone: on ? "beacon-on" : "beacon-off" },
    line: fixedLine(status, radios, nowMs),
    hover: last === null ? undefined : dateTimeText(last),
    radios: radioLines(radios, nowMs),
  };
}

/**
 * The block for the last `status`, the `gps` topic and the settings in force (`values`). `radios`
 * lists the radios the beacon goes out on (empty with one radio). `receiveOnly`: nothing is sent.
 * A station moves when the daemon says its beacon follows the GPS, else when the settings say so.
 */
export function beaconBlock(
  status: StatusMessage | null,
  gps: GpsState | null,
  values: Readonly<Record<string, string>>,
  nowMs: number,
  radios: readonly BeaconRadio[] = [],
  receiveOnly = false,
): BeaconBlock {
  const moving = gps === null ? isMoving(values) : gps.mobile;
  const rxOnly = receiveOnly || values["station/transmit"] === "false";
  const quiet = rxOnly ? t("error.transmit.off") : beaconOff(values) ? t("beacon.line.off") : "";
  if (moving) return movingBlock(gps, values, nowMs, quiet, radios);
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
  return fixedBlock(status, radios, nowMs);
}

// ---- the radios of the Beacon group: Send on ticks and Path rows

/** The per-radio field a Send on tick sets. */
export type SendOnField = "beacon" | "status" | "ask" | "local_info";

/**
 * The radios a thing with a Send on goes out on, as the daemon applies it (neoaprs/beaconrule.py):
 * with one radio on, that one; else the radios whose tick is set, none if none is.
 */
function sendOnRadios(field: SendOnField, enabled: readonly PageRadio[]): PageRadio[] {
  if (enabled.length <= 1) return [...enabled];
  return enabled.filter((radio) => radio.row.choices[field]);
}

/** The radios the beacon goes out on. */
export const beaconRadios = (enabled: readonly PageRadio[]): PageRadio[] => sendOnRadios("beacon", enabled);

/** The radios the status report goes out on. */
export const statusRadios = (enabled: readonly PageRadio[]): PageRadio[] => sendOnRadios("status", enabled);

/**
 * Why a send button is off when none of `radios` is connected (one line per radio); else undefined.
 */
export function notConnectedWhy(radios: readonly PageRadio[]): string | undefined {
  if (radios.some((radio) => radio.connected)) return undefined;
  return radios.map((radio) => t("radio.not_connected", { name: radio.name })).join("\n") || undefined;
}

/** The key of a radio's own setting (`radio/3/beacon`). */
const radioKey = (id: RadioId, key: string): string => `radio/${id}/${key}`;

/**
 * One Send on tick. `last` is the only ticked one (greyed so the thing still goes out somewhere).
 */
export interface SendOnTick {
  id: RadioId;
  key: string;
  name: string;
  on: boolean;
  last: boolean;
}

/**
 * One Send on tick per enabled radio, in box order. `ticked` says whether a radio's tick is set as
 * it is being edited. If none is ticked, no tick is ticked or greyed.
 */
export function sendOnTicks(enabled: readonly PageRadio[], ticked: (key: string, radio: PageRadio) => boolean, field: SendOnField = "beacon"): SendOnTick[] {
  const ticks = enabled.map((radio) => {
    const key = radioKey(radio.id, field);
    return { id: radio.id, key, name: radio.name, on: ticked(key, radio), last: false };
  });
  const on = ticks.filter((tick) => tick.on);
  return on.length === 1 ? ticks.map((tick) => (tick.on ? { ...tick, last: true } : tick)) : ticks;
}

/** One Path row: its setting key, its radio and the radio's name (null with one radio on). */
export interface PathRow {
  key: string;
  radio: RadioId;
  name: string | null;
}

/** The setting key of a radio's path. */
export const pathKey = (radio: Pick<PageRadio, "id">): string => radioKey(radio.id, "path");

/** One Path row per enabled radio that can carry a path; named only while several radios are on. */
export function pathRows(enabled: readonly PageRadio[]): PathRow[] {
  const carrying = enabled.filter((radio) => radio.carriesPath);
  const several = enabled.length > 1;
  return carrying.map((radio) => ({ key: pathKey(radio), radio: radio.id, name: several ? radio.name : null }));
}

/** A radio's own setting in force: from the settings' values, else `config.radio_values`. */
export function radioValueOf(config: Pick<ConfigValues, "values" | "radio_values"> | null, key: string): string | undefined {
  return config?.values[key] ?? config?.radio_values[key];
}
