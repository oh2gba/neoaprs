// What the status row of the Status group of the Beacon tab says (components/StatusReportRow.vue): not the text, which the Text field above it shows, but when a report last went and when the next may. The next is the interval after the last, and goes out then only if what it says has changed
// (services/rigstatus.py); while the beacon is Off no status goes by the timer. In RX only (nothing is sent) the row is off in the warn colour, as the Digipeater's.
import { t } from "@/i18n";
import { agoWords, untilText } from "@/lib/format";

export interface ReportLook {
  state: string;
  /** the class that colours the state */
  tone: string;
  line: string;
}

/** The look for the time of the last report (ISO, null for none), the interval in minutes as the settings hold it, whether the beacon is Off (no timed status), whether transmitting is switched off, and the time now. */
export function reportLook(lastSent: string | null, minutes: string, beaconOff: boolean, rxOnly: boolean, nowMs: number): ReportLook {
  if (rxOnly) return { state: t("beacon.state.off"), tone: "tnc-waiting", line: t("beacon.line.rx_only") };
  const on = { state: t("beacon.state.on"), tone: "beacon-on" };
  if (lastSent === null) return { ...on, line: t("beacon.status.line.none") };
  const ago = agoWords(lastSent, nowMs);
  const every = Number(minutes);
  if (beaconOff || !(every > 0)) return { ...on, line: t("beacon.status.line.untimed", { ago }) };
  const nextAt = new Date(new Date(lastSent).getTime() + every * 60_000).toISOString();
  return { ...on, line: t(Date.parse(nextAt) > nowMs ? "beacon.status.line.timed" : "beacon.status.line.due", { ago, when: untilText(nextAt, nowMs) }) };
}
