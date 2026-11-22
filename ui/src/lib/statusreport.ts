// What the Status group's status row says (components/StatusReportRow.vue): not the text, but when
// a report last went and when the next is due. The next is the interval after the last, and goes
// out then whether or not the text changed (services/rigstatus.py), as "now" once due; while the
// beacon is Off no status goes by the timer. In RX only the row is off in the warn colour, as the
// Digipeater's.
import { t } from "@/i18n";
import { agoWords, untilText } from "@/lib/format";
import type { RadioStatusState } from "@/protocol/protocol";

export interface ReportLook {
  state: string;
  /** The class that colours the state. */
  tone: string;
  line: string;
}

/**
 * The look for the last report's time (ISO, null for none), the interval in minutes as the settings
 * hold it, whether no timed status goes (the beacon is Off, or the status is ticked for no radio
 * that is on), whether transmitting is off, whether the status is ticked for no radio that is on
 * (nothing can send it: the pill off, as the beacon's), and the time now.
 */
export function reportLook(
  lastSent: string | null,
  minutes: string,
  beaconOff: boolean,
  rxOnly: boolean,
  nowhere: boolean,
  nowMs: number,
): ReportLook {
  if (rxOnly) return { state: t("beacon.state.off"), tone: "tnc-waiting", line: t("error.transmit.off") };
  const on = nowhere
    ? { state: t("beacon.state.off"), tone: "beacon-off" }
    : { state: t("beacon.state.on"), tone: "beacon-on" };
  if (lastSent === null) return { ...on, line: t("beacon.status.line.none") };
  const ago = agoWords(lastSent, nowMs);
  const every = Number(minutes);
  if (beaconOff || !(every > 0)) return { ...on, line: t("beacon.status.line.untimed", { ago }) };
  const sentMs = Date.parse(lastSent);
  if (Number.isNaN(sentMs)) return { ...on, line: t("beacon.status.line.untimed", { ago }) };
  const nextAt = new Date(sentMs + every * 60_000).toISOString();
  return { ...on, line: t("beacon.status.line.timed", { ago, when: untilText(nextAt, nowMs), minutes: every }) };
}

/**
 * The lines behind the arrow while several radios are on: the status on each radio it goes out on,
 * by name ("HF: last sent 2 min ago · next in 28 min (every 30 min)").
 */
export function statusRadioLines(
  radios: readonly { name: string; status: RadioStatusState }[],
  nowMs: number,
): string[] {
  return radios.map(({ name, status }) => {
    const { last_sent: last, next_due: next, interval_min: minutes } = status;
    const ago = agoWords(last, nowMs);
    const line =
      last === null
        ? t("beacon.status.fold.none")
        : minutes > 0 && next !== null
          ? t("beacon.status.fold.timed", { ago, when: untilText(next, nowMs), minutes })
          : t("beacon.status.fold.untimed", { ago });
    return t("radio.line", { name, line });
  });
}
