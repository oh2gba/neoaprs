// What the beacon status at the top of the My station tab says (components/BeaconStatus.vue), in the look of the radio status: a label, one coloured pill and plain lines. A fixed station says when the last beacon went and when the timer sends the next
// ("Last beacon 4 min ago · next in 56 min (every 60 min)"); a moving station says the GPS (the pill is the state of the GPS, the line the fix or why there is none) and, under it, what SmartBeaconing does (lib/gpsstatus.ts has those words).
// While the beacon is Off (the interval is 0) a fixed station has the label Beacon, the pill off and the line "no automatic beacon · Beacon now still sends"; a moving station keeps showing the GPS (the pill and the fix line, so that the fix can be watched) and says the same on the line under it, where SmartBeaconing's words would be.
// In RX only (nothing is sent) the pill is off in the warn colour and the line "RX only: nothing is sent", as the Digipeater's; a moving station keeps the GPS and says it under it.
// While several radios are on, behind the arrow is a line for each radio the beacon goes out on, by its name, with its own interval ("HF: last beacon 2 min ago · next in 29 min (every 30 min)"). The end of the file is the rest
// of the Beacon group's radios (BeaconPane.vue, SettingsPath.vue): the radios the beacon goes out on, the ticks of Send on, and a Path row for each radio that may carry a path.
import { t } from "@/i18n";
import { dateTimeText, agoWords, untilText } from "@/lib/format";
import { beaconOff } from "@/lib/beaconoff";
import { gpsProblem, gpsStateText, gpsStatus, isMoving, mobileBeaconText } from "@/lib/gpsstatus";
import type { PageRadio, RadioId } from "@/lib/radios";
import type { ConfigValues, GpsState, RadioBeaconState, StatusMessage } from "@/protocol/protocol";

/** A radio the beacon goes out on, as its line behind the arrow says it: its name, its own beacon timer (the row of the topic `radios`) and whether it does SmartBeaconing (a moving station's beacon there follows the GPS, not an interval). */
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
  /** the word on the pill and the class that colours it; null while the daemon has not told yet */
  pill: { text: string; tone: string } | null;
  /** the first line */
  line: string;
  /** the full time of the last beacon, on hover, for a fixed station that has sent one */
  hover: string | undefined;
  /** the SmartBeaconing line of a moving station */
  smart: string | null;
  /** one quiet line for each radio the beacon goes out on ("FM: last beacon 4 min ago · next in 26 min (every 20 min)"), only while several radios are on: the row's line is the latest and the soonest of them, these are the detail, each with its own interval */
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

/** The beacons the daemon told. While several radios are on, the radios' own (`radios`, each its row's timer); else the status's (`beacon_*`: the latest on any radio and the next due on any). The row's line is the latest beacon on any radio and the next due on any radio. */
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

/** Whether the timer will send a beacon: the interval is not 0 and the daemon has a time for the next. */
const timed = (status: StatusMessage, radios: readonly BeaconRadio[]): boolean => status.beacon_interval_min > 0 && times(status, radios).next !== null;

/** The line of a fixed station: the last beacon and the timer, "Last beacon 4 min ago · next in 56 min (every 60 min)" (the interval is the shortest of the radios the beacon goes out on, as the daemon tells it). */
function fixedLine(status: StatusMessage, radios: readonly BeaconRadio[], nowMs: number): string {
  const { last, next } = times(status, radios);
  const ago = agoWords(last, nowMs);
  const never = last === null;
  if (!timed(status, radios)) return never ? t("beacon.line.untimed_none") : t("beacon.line.untimed", { ago });
  const values = { when: untilText(next, nowMs), minutes: status.beacon_interval_min };
  return never ? t("beacon.line.timed_none", values) : t("beacon.line.timed", { ago, ...values });
}

/** The line of one radio's beacon, with the interval in force on it: "last beacon 4 min ago · next in 26 min (every 30 min)". A radio whose beacon follows the GPS (`smart`: a moving station's radio with SmartBeaconing) has
 * no interval: its next is the one by time that SmartBeaconing says. */
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

/** The lines behind the arrow while several radios are on: each radio's beacon, by its name (`moving`: the radios with SmartBeaconing follow the GPS, the others keep their interval). */
const radioLines = (radios: readonly BeaconRadio[], nowMs: number, moving = false): string[] =>
  radios.map((radio) => t("radio.line", { name: radio.name, line: radioLine(radio.beacon, nowMs, moving && radio.smart) }));

/** The block of a moving station: the GPS, and under it SmartBeaconing's words, or why nothing is sent (`quiet`, empty when something is); while several radios are on, a line for each radio the beacon goes out on, for a radio
 * without SmartBeaconing sends the timed beacon with the latest fix (plan rule 3.1). */
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

/** The block of a fixed station whose beacon is not Off: on or off by the timer, the line of the latest and the next beacon, the full time of the latest on hover, and a line for each radio while several are on. */
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

/** The block for the status the daemon last told (`status`), the GPS topic (`gps`), the settings in force (`values`), the time now and, while several radios are on, the radios the beacon goes out on (`radios`, none
 * while one is); `receiveOnly`: nothing is sent (RX only, or no radio that is on can send: the page's `receiveOnly`). A station moves when the daemon says its beacon follows the GPS, before it has told when the settings say so. */
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
  const quiet = rxOnly ? t("beacon.line.rx_only") : beaconOff(values) ? t("beacon.line.off") : "";
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

// ---- the radios of the Beacon group: the beacon's, the ticks of Send on, the Path rows

/** The radios the beacon goes out on, as the daemon has them in force (plan rule 3.1): with one radio on, that one whatever its Send on says; else those whose Send on is ticked, and the main radio when none is. */
export function beaconRadios(enabled: readonly PageRadio[], main: PageRadio | null): PageRadio[] {
  if (enabled.length <= 1) return [...enabled];
  const ticked = enabled.filter((radio) => radio.row.choices.beacon);
  return ticked.length > 0 ? ticked : main === null ? [] : [main];
}

/** Why a button that sends on these radios is off while none of them is connected: "FM: not connected", a line for each; undefined while one is. */
export function notConnectedWhy(radios: readonly PageRadio[]): string | undefined {
  if (radios.some((radio) => radio.connected)) return undefined;
  return radios.map((radio) => t("radio.not_connected", { name: radio.name })).join("\n") || undefined;
}

/** The key of a radio's own setting (`radio/3/beacon`). */
const radioKey = (id: RadioId, key: string): string => `radio/${id}/${key}`;

/** One tick of Send on: the radio, its setting, its name, whether it is ticked, whether it is the last tick that is (greyed: the beacon is switched off by the interval alone), and whether it is ticked only because the
 * beacon goes out on it while no radio that is on is ticked (`held`: the main radio's; a tick of another radio keeps it ticked, as it was seen). */
export interface SendOnTick {
  id: RadioId;
  key: string;
  name: string;
  on: boolean;
  last: boolean;
  held: boolean;
}

/** The ticks of Send on, one for each radio that is on, in the order of the boxes; `ticked` says whether a radio's is ticked as it is being set (`radio/<id>/beacon`). They show what is in force (plan rule 3.1): while none
 * is ticked the beacon goes out on the main radio, so its tick is the one ticked and greyed. */
export function sendOnTicks(enabled: readonly PageRadio[], ticked: (key: string, radio: PageRadio) => boolean, main: PageRadio | null): SendOnTick[] {
  const ticks = enabled.map((radio) => {
    const key = radioKey(radio.id, "beacon");
    return { id: radio.id, key, name: radio.name, on: ticked(key, radio), last: false, held: false };
  });
  const none = !ticks.some((tick) => tick.on);
  const shown = none ? ticks.map((tick) => (tick.id === main?.id ? { ...tick, on: true, held: true } : tick)) : ticks;
  const on = shown.filter((tick) => tick.on);
  return on.length === 1 ? shown.map((tick) => (tick.on ? { ...tick, last: true } : tick)) : shown;
}

/** One Path row of the Advanced fold: the setting it writes, its radio, and the radio's name (null while one radio is on, so that the row is "Path" as it was). */
export interface PathRow {
  key: string;
  radio: RadioId;
  name: string | null;
}

/** The setting of a radio's path: its own `radio/<id>/path`. */
export const pathKey = (radio: Pick<PageRadio, "id">): string => radioKey(radio.id, "path");

/** The Path rows: one for each radio that is on and may carry a path, named while several radios are on (one radio's row is "Path", as it was). */
export function pathRows(enabled: readonly PageRadio[]): PathRow[] {
  const carrying = enabled.filter((radio) => radio.carriesPath);
  const several = enabled.length > 1;
  return carrying.map((radio) => ({ key: pathKey(radio), radio: radio.id, name: several ? radio.name : null }));
}

/** A radio's own setting as the page has it in force: in the settings' values once they hold the radios' keys, else in `config.radio_values`; undefined for none. */
export function radioValueOf(config: Pick<ConfigValues, "values" | "radio_values"> | null, key: string): string | undefined {
  return config?.values[key] ?? config?.radio_values[key];
}

/** The draft of a radio's own setting that the settings' values do not hold (only `config.radio_values` has it) follows the value in force where it was not changed since, as the settings' own keys do
 * (composables/useSettingsAnswers.ts); a key the values hold is theirs. `now` and `before` are the values in force of the keys, by key. */
export function followRadioValues(
  draft: Record<string, string>,
  values: Readonly<Record<string, string>>,
  now: Readonly<Record<string, string>>,
  before: Readonly<Record<string, string>> | undefined,
): void {
  for (const [key, text] of Object.entries(now)) if (!(key in values) && key in draft && draft[key] === before?.[key]) draft[key] = text;
}
