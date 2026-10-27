// The marks at the top right of the header, before the count of messages, each with a short hover title and the place where it is set. In this order (Update first, when a newer version is known), which is the order they fold in on a narrow screen (the last first): Daemon (in a browser only: ok while the page is connected, warn while it connects, bad when it is offline; in the app page and daemon are one),
// Radio (always: ok while connected, the Dummy radio dummy, else warn with the state in words; it opens Settings → Radio), RX only (warn, while transmitting is off), Beacon off (neutral, only while transmitting is on),
// GPS (only when a GPS is the position source: ok with a fix, warn without), Internet (info, while Internet stations is connected and receiving), Map (info, while the detailed map is being downloaded: the percent of the step; it opens Settings → Map). Plain functions of the settings and the states the daemon told; the marks are the TagMark of the page: RX only is warn, Beacon off neutral, Internet info, GPS ok with a fix and warn without.
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import type { Params } from "@/i18n/message";
import { beaconOff } from "@/lib/beaconoff";
import { isMoving } from "@/lib/gpsstatus";
import { silentText } from "@/lib/format";
import type { Connection } from "@/lib/hub";
import type { GpsState, IgateState, MapState, TncState, UpdateInfo } from "@/protocol/protocol";
import type { TagTone } from "@/components/TagMark.vue";

/** Where a mark leads: the Settings tab (the Radio and Internet groups) or the Beacon tab (the beacon and the GPS). */
export type PillTarget = "settings" | "beacon";

export interface HeaderPill {
  id: "update" | "daemon" | "radio" | "rx" | "beacon_off" | "internet" | "gps" | "map";
  text: MessageId;
  textValues?: Params;
  title: MessageId;
  /** the values of the title (the newer version) */
  titleValues?: Params;
  tone: TagTone;
  /** where a click leads; null for a mark that only says (the daemon's: there is nothing to open) */
  target: PillTarget | null;
  /** the id of the control the mark leads to: its group is brought into view and flashed (lib/attention.ts) */
  focus: string;
}

/** What the page knows of the link to the daemon and to the radio: the socket, the radio's state and the time now (for how long the radio has been silent), and whether the page is the desktop app's (lib/shell.ts), where page and daemon are one and there is no Daemon mark. */
export interface Link {
  connection: Connection;
  tnc: TncState | null;
  now: number;
  inApp: boolean;
}

/** The Daemon mark: how the page's socket stands. */
function daemonPill(connection: Connection): HeaderPill {
  const states = {
    open: { text: "pill.daemon", title: "pill.daemon_title", tone: "ok" },
    connecting: { text: "pill.daemon_connecting", title: "pill.daemon_connecting_title", tone: "warn" },
    closed: { text: "pill.daemon_offline", title: "pill.daemon_offline_title", tone: "bad" },
  } as const;
  return { id: "daemon", ...states[connection], target: null, focus: "" };
}

/** The Radio mark: the state of the radio link, which is unknown (waiting) while the page's socket is not open. Settings → Radio is where it leads. */
function radioPill(link: Link): HeaderPill {
  const base = { id: "radio", target: "settings", focus: "set-tnc-profile" } as const;
  const why = (text: string) => ({ title: "pill.radio_why_title", titleValues: { why: text } }) as const;
  const radio = link.connection === "open" ? link.tnc : null;
  if (radio === null) return { ...base, text: "pill.radio_waiting", tone: "warn", ...why(t("pill.radio_waiting_why")) };
  if (radio.state === "connected") {
    return radio.dummy
      ? { ...base, text: "pill.radio", title: "pill.radio_dummy_title", tone: "dummy" }
      : { ...base, text: "pill.radio", title: "pill.radio_title", tone: "ok" };
  }
  if (radio.state === "silent") return { ...base, text: "pill.radio_silent", tone: "warn", ...why(silentText(radio.silent_since, link.now)) };
  const reason = radio.problem || radio.describe || radio.state;
  if (radio.state === "connecting") {
    return { ...base, text: radio.describe.includes("entering KISS") ? "pill.radio_kiss" : "pill.radio_searching", tone: "warn", ...why(reason) };
  }
  return { ...base, text: "pill.radio_off", tone: "warn", ...why(reason) };
}

/** The Update mark, while a newer version is known. */
const updatePill = (update: UpdateInfo): HeaderPill => ({
  id: "update",
  text: "pill.update",
  title: "pill.update_title",
  titleValues: { version: update.version },
  tone: "accent",
  target: "settings",
  focus: "set-update-now",
});

/** RX only while transmitting is off, else Beacon off while the beacon is (nothing, when neither). */
function sendingPill(values: Readonly<Record<string, string>>): HeaderPill | null {
  if (values["station/transmit"] === "false") {
    return { id: "rx", text: "pill.rx", title: "pill.rx_title", tone: "warn", target: "settings", focus: "set-station-transmit" };
  }
  if (!beaconOff(values)) return null;
  return { id: "beacon_off", text: "pill.beacon_off", title: "pill.beacon_off_title", tone: "neutral", target: "beacon", focus: "set-beacon-interval_min" };
}

/** GPS, only when a GPS is the position source: ok with a fix, warn without. */
function gpsPill(values: Readonly<Record<string, string>>, gps: GpsState | null): HeaderPill | null {
  if (!(gps === null ? isMoving(values) : gps.mobile)) return null;
  const fix = gps?.state === "fix";
  return {
    id: "gps",
    text: "pill.gps",
    title: fix ? "pill.gps_fix_title" : "pill.gps_nofix_title",
    tone: fix ? "ok" : "warn",
    target: "beacon",
    focus: "set-gps-source",
  };
}

/** Internet, while Internet stations is enabled and connected. */
function internetPill(igate: IgateState | null): HeaderPill | null {
  const up = igate !== null && igate.enabled && (igate.state === "connected" || igate.state === "listening" || igate.state === "unverified");
  return up ? { id: "internet", text: "pill.internet", title: "pill.internet_title", tone: "info", target: "settings", focus: "set-igate-enabled" } : null;
}

/** The Map mark while the detailed map is being downloaded (the job of Settings → Map, or the one begun by itself after the setup): the percent of its step when it is known. */
function mapPill(map: MapState | null): HeaderPill | null {
  if (map === null || map.state !== "downloading") return null;
  const base = { id: "map", title: "pill.map_title", tone: "info", target: "settings", focus: "set-map-fetch" } as const;
  return map.percent === null ? { ...base, text: "pill.map_working" } : { ...base, text: "pill.map", textValues: { percent: map.percent } };
}

/** The marks for these settings (key to text) and states; the states are null until the daemon has told. `link` is how the page stands to the daemon and the radio (null: no Daemon or Radio mark). */
export function headerPills(
  values: Readonly<Record<string, string>>,
  gps: GpsState | null,
  igate: IgateState | null,
  update: UpdateInfo | null = null,
  link: Link | null = null,
  map: MapState | null = null,
): HeaderPill[] {
  const linked = link === null ? [] : [...(link.inApp ? [] : [daemonPill(link.connection)]), radioPill(link)];
  const marks = [update === null ? null : updatePill(update), ...linked, sendingPill(values), gpsPill(values, gps), internetPill(igate), mapPill(map)];
  return marks.filter((mark): mark is HeaderPill => mark !== null);
}
