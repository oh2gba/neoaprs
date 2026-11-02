// The marks at the top right of the header, before the count of messages, each with a short hover title and the place where it is set. In this order (Update first, when a newer version is known), which is the order they fold in on a narrow screen (the last first): Daemon (in a browser only: ok while the page is connected, warn while it connects, bad when it is offline; in the app page and daemon are one),
// Radio (always: ok while connected, the Dummy radio dummy, else warn with the state in words; it opens Settings → Radio; while the HF radio is ticked it is two marks, FM and HF, each in the state of its own radio, and with FM unticked the HF mark alone), RX only (warn, while transmitting is off), Beacon off (neutral, only while transmitting is on),
// GPS (only when a GPS is the position source: ok with a fix, warn without), Internet (info, while Internet stations is connected and receiving), Map (info, while the detailed map is being downloaded: the percent of the step; it opens Settings → Map). Plain functions of the settings and the states the daemon told; the marks are the TagMark of the page: RX only is warn, Beacon off neutral, Internet info, GPS ok with a fix and warn without.
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import type { Params } from "@/i18n/message";
import { beaconOff } from "@/lib/beaconoff";
import { isMoving } from "@/lib/gpsstatus";
import { silentText } from "@/lib/format";
import type { Connection } from "@/lib/hub";
import { fmOn, hfOn } from "@/lib/radiosides";
import type { GpsState, IgateState, MapState, TncState, UpdateInfo } from "@/protocol/protocol";
import type { TagTone } from "@/components/TagMark.vue";

/** Where a mark leads: the Settings tab (the Radio and Internet groups) or the My station tab (the beacon and the GPS). */
export type PillTarget = "settings" | "beacon";

export interface HeaderPill {
  id: "update" | "daemon" | "radio" | "fm" | "hf" | "rx" | "beacon_off" | "internet" | "gps" | "map";
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

/** What the page knows of the link to the daemon and to the radios: the socket, the FM radio's state (`tnc`), the HF radio's (`hf`) and the time now (for how long a radio has been silent), and whether the page is the desktop app's (lib/shell.ts), where page and daemon are one and there is no Daemon mark. */
export interface Link {
  connection: Connection;
  tnc: TncState | null;
  hf: TncState | null;
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

/** The mark of a radio: the state of its link, which is unknown (waiting) while the page's socket is not open. Settings → Radio is where it leads, to the control `focus` (inside the radio's box, which is flashed). `named` is "FM radio" or "HF radio" where there are two marks, and the mark says "Radio" (today's words) where there is one. */
function radioPill(link: Link, radio: TncState | null, id: HeaderPill["id"], focus: string, named: MessageId | null): HeaderPill {
  const base = { id, target: "settings", focus } as const;
  const values = named === null ? undefined : { radio: t(named) };
  const word = (plain: MessageId, withName: MessageId) => ({ text: named === null ? plain : withName, textValues: values }) as const;
  const why = (text: string) => ({ title: "pill.radio_why_title", titleValues: { why: text } }) as const;
  const state = link.connection === "open" ? radio : null;
  if (state === null) return { ...base, ...word("pill.radio_waiting", "pill.radio_named_waiting"), tone: "warn", ...why(t("pill.radio_waiting_why")) };
  if (state.state === "connected") {
    if (state.dummy) return { ...base, text: named ?? "pill.radio", title: "pill.radio_dummy_title", tone: "dummy" };
    return named === null
      ? { ...base, text: "pill.radio", title: "pill.radio_title", tone: "ok" }
      : { ...base, text: named, title: "pill.radio_named_title", titleValues: values, tone: "ok" };
  }
  if (state.state === "silent")
    return { ...base, ...word("pill.radio_silent", "pill.radio_named_silent"), tone: "warn", ...why(silentText(state.silent_since, link.now)) };
  const reason = state.problem || state.describe || state.state;
  if (state.state === "connecting") {
    return state.describe.includes("entering KISS")
      ? { ...base, ...word("pill.radio_kiss", "pill.radio_named_kiss"), tone: "warn", ...why(reason) }
      : { ...base, ...word("pill.radio_searching", "pill.radio_named_searching"), tone: "warn", ...why(reason) };
  }
  return { ...base, ...word("pill.radio_off", "pill.radio_named_off"), tone: "warn", ...why(reason) };
}

/** The radio marks: one radio on is the one Radio mark, whichever radio it is (the page names a radio only where there are two); both on are two marks, FM radio and HF radio, each in the state of its own radio. */
function radioPills(link: Link, values: Readonly<Record<string, string>>): HeaderPill[] {
  const fm = fmOn(values);
  const hf = hfOn(values);
  if (fm && hf) {
    return [radioPill(link, link.tnc, "fm", "set-tnc-profile", "pill.fm_radio"), radioPill(link, link.hf, "hf", "set-mercury-sound_card", "pill.hf_radio")];
  }
  return [fm || !hf ? radioPill(link, link.tnc, "radio", "set-tnc-profile", null) : radioPill(link, link.hf, "radio", "set-mercury-sound_card", null)];
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
  const linked = link === null ? [] : [...(link.inApp ? [] : [daemonPill(link.connection)]), ...radioPills(link, values)];
  const marks = [update === null ? null : updatePill(update), ...linked, sendingPill(values), gpsPill(values, gps), internetPill(igate), mapPill(map)];
  return marks.filter((mark): mark is HeaderPill => mark !== null);
}
