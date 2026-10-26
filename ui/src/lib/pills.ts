// The marks at the top right of the header, before the count of messages: only what is out of the ordinary or running, each with a short hover title and the place where it is set. In this order, which is the order they fold in on a narrow screen (the last first): RX only (warn, while transmitting is off), Beacon off (neutral, only while transmitting is on),
// GPS (only when a GPS is the position source: ok with a fix, warn without), Internet (info, while Internet stations is connected and receiving). Plain functions of the settings and the states the daemon told; the marks are the TagMark of the page: RX only is warn, Beacon off neutral, Internet info, GPS ok with a fix and warn without.
import type { MessageId } from "@/i18n/catalogue";
import { beaconOff } from "@/lib/beaconoff";
import { isMoving } from "@/lib/gpsstatus";
import type { GpsState, IgateState } from "@/protocol/protocol";
import type { TagTone } from "@/components/TagMark.vue";

/** Where a mark leads: the Settings tab (the Radio and Internet groups) or the Beacon tab (the beacon and the GPS). */
export type PillTarget = "settings" | "beacon";

export interface HeaderPill {
  id: "rx" | "beacon_off" | "internet" | "gps";
  text: MessageId;
  title: MessageId;
  tone: TagTone;
  target: PillTarget;
  /** the id of the control the mark leads to: its group is brought into view and flashed (lib/attention.ts) */
  focus: string;
}

/** The marks for these settings (key to text) and states; the states are null until the daemon has told. */
export function headerPills(values: Readonly<Record<string, string>>, gps: GpsState | null, igate: IgateState | null): HeaderPill[] {
  const pills: HeaderPill[] = [];
  const rxOnly = values["station/transmit"] === "false";
  if (rxOnly) pills.push({ id: "rx", text: "pill.rx", title: "pill.rx_title", tone: "warn", target: "settings", focus: "set-station-transmit" });
  else if (beaconOff(values))
    pills.push({
      id: "beacon_off",
      text: "pill.beacon_off",
      title: "pill.beacon_off_title",
      tone: "neutral",
      target: "beacon",
      focus: "set-beacon-interval_min",
    });
  if (gps === null ? isMoving(values) : gps.mobile) {
    const fix = gps?.state === "fix";
    pills.push({
      id: "gps",
      text: "pill.gps",
      title: fix ? "pill.gps_fix_title" : "pill.gps_nofix_title",
      tone: fix ? "ok" : "warn",
      target: "beacon",
      focus: "set-gps-source",
    });
  }
  if (igate !== null && igate.enabled && (igate.state === "connected" || igate.state === "listening" || igate.state === "unverified")) {
    pills.push({ id: "internet", text: "pill.internet", title: "pill.internet_title", tone: "info", target: "settings", focus: "set-igate-enabled" });
  }
  return pills;
}
