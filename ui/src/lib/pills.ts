// The marks at the top right of the header, before the count of messages, each with a short hover title and the place where it is set. In this order (Update first, when a newer version is known), which is the order they fold in on a narrow screen (the last first): Daemon (in a browser only: ok while the page is connected, warn while it connects, bad when it is offline; in the app page and daemon are one),
// the radios (none while the daemon has told that the station has no radio; while the socket is not open, waiting, with the Daemon mark's words as the title; one radio on: the Radio mark as it always was, ok while connected, the Dummy radio dummy, else warn with the state in words; two on: a mark each with its short name in place of "Radio"; three and more: one mark "Radios", warn and naming the radio in trouble ("20 m: not connected") or the count of them ("Radios: 2 not connected"), its title each radio with its state, dashed only when every radio is a Dummy; each leads to Settings → Radio, to the radio's box or the first in trouble), RX only (warn, while transmitting is off), Beacon off (neutral, only while transmitting is on),
// GPS (only when a GPS is the position source: ok with a fix, warn without), Internet (info, while Internet stations is connected and receiving), Map (info, while the detailed map is being downloaded: the percent of the step; it opens Settings → Map). Plain functions of the settings, the radios and the states the daemon told; the marks are the TagMark of the page: RX only is warn, Beacon off neutral, Internet info, GPS ok with a fix and warn without.
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import type { Params } from "@/i18n/message";
import { beaconOff } from "@/lib/beaconoff";
import { isMoving } from "@/lib/gpsstatus";
import { silentText } from "@/lib/format";
import type { Connection } from "@/lib/hub";
import { enabledRadios, problemText, type PageRadio, type RadioId } from "@/lib/radios";
import { enableId } from "@/lib/settingsradio";
import type { GpsState, IgateState, MapState, RadioRow, UpdateInfo } from "@/protocol/protocol";
import type { TagTone } from "@/components/TagMark.vue";

/** Where a mark leads: the Settings tab (the Radio and Internet groups) or the My station tab (the beacon and the GPS). */
export type PillTarget = "settings" | "beacon";

export interface HeaderPill {
  id: "update" | "daemon" | "radio" | `radio-${RadioId}` | "radios" | "rx" | "beacon_off" | "internet" | "gps" | "map";
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

/** What the page knows of the link to the daemon and to the radios: the socket, the radios (composables/useRadios.ts `all`) and whether the daemon has told them yet (`told`: a station with no radio has none to
 * wait for), the time now (for how long a radio has been silent), and whether the page is the desktop app's (lib/shell.ts), where page and daemon are one and there is no Daemon mark. */
export interface Link {
  connection: Connection;
  now: number;
  inApp: boolean;
  radios: readonly PageRadio[];
  told: boolean;
}

/** The words of the Daemon mark for each state of the socket: a radio's mark says the same while the socket is not open (nothing is known of the radio then, and it is the link to NeoAPRS that is away). */
const DAEMON_STATES = {
  open: { text: "pill.daemon", title: "pill.daemon_title", tone: "ok" },
  connecting: { text: "pill.daemon_connecting", title: "pill.daemon_connecting_title", tone: "warn" },
  closed: { text: "pill.daemon_offline", title: "pill.daemon_offline_title", tone: "bad" },
} as const;

/** The Daemon mark: how the page's socket stands. */
function daemonPill(connection: Connection): HeaderPill {
  return { id: "daemon", ...DAEMON_STATES[connection], target: null, focus: "" };
}

/** The line of a radio as a mark says it: its state, whether it is a Dummy, since when it is silent and why it is not connected; null while nothing is known of it. */
interface Line {
  state: RadioRow["state"];
  dummy: boolean;
  since: string | null;
  why: string;
}

/** Why a radio is not connected, in the words of the page: its coded problem (lib/radios.ts `problemText`), searching while its line is being opened, else its state; never the daemon's line of what it does
 * (that names ports and devices: the log has it). */
function whyOf(state: RadioRow["state"], radio: PageRadio | undefined, radios: readonly PageRadio[] = []): string {
  const problem = radio?.problem ?? null;
  if (state === "connecting" && (problem === null || problem.code === "radio.not_connected")) return t("settings.tnc.searching");
  return problem === null ? t(`settings.tnc.state.${state}`) : problemText(problem, t, { byId: (id) => radios.find((one) => one.id === id) });
}

/** The line of a radio by its row of the topic `radios`. */
function lineOfRow(radio: PageRadio, radios: readonly PageRadio[]): Line {
  const since = radio.problem?.code === "radio.silent" ? String(radio.problem.params["since"] ?? "") : "";
  return {
    state: radio.state,
    dummy: radio.dummy,
    since: since === "" ? null : since,
    why: whyOf(radio.state, radio, radios),
  };
}

/** The line of a radio by its row of the topic `radios`; unknown (waiting) while the page's socket is not open, and for no radio. */
function lineOf(link: Link, radio: PageRadio | undefined): Line | null {
  return link.connection !== "open" || radio === undefined ? null : lineOfRow(radio, link.radios);
}

/** The control a radio's mark leads to, inside its box in Settings → Radio (which is flashed): its Enable; Add radio while the station has none. */
function radioFocus(radio: Pick<PageRadio, "id"> | undefined): string {
  return radio === undefined ? "set-radio-add" : enableId(radio);
}

/** The title "{why}. Settings → Radio": the reason without a stop of its own (the title puts its stop after it). */
const whyTitle = (text: string) => ({ title: "pill.radio_why_title", titleValues: { why: text.replace(/[.…。]+$/u, "") } }) as const;

/** The mark of a radio in the state of its line. `name` is the radio's short name where it is named (two marks), and the mark says "Radio" (the words it always had) where there is one. */
function radioPill(link: Link, line: Line | null, id: HeaderPill["id"], focus: string, name: string | null): HeaderPill {
  const base = { id, target: "settings", focus } as const;
  const values = name === null ? undefined : { radio: name, name }; // (`name` for the shared words of a radio: "{name}: not connected")
  const word = (plain: MessageId, withName: MessageId) => ({ text: name === null ? plain : withName, textValues: values }) as const;
  if (line === null) {
    const title = link.connection === "open" ? whyTitle(t("pill.radio_waiting_why")) : { title: DAEMON_STATES[link.connection].title }; // (the socket away: what the Daemon mark says)
    return { ...base, ...word("pill.radio_waiting", "pill.radio_named_waiting"), tone: "warn", ...title };
  }
  if (line.state === "connected") {
    if (line.dummy) return { ...base, ...word("pill.radio", "pill.radio_named"), title: "pill.radio_dummy_title", tone: "dummy" };
    return name === null
      ? { ...base, text: "pill.radio", title: "pill.radio_title", tone: "ok" }
      : {
          ...base,
          text: "pill.radio_named",
          textValues: values,
          tone: "ok",
          ...whyTitle(t("radio.line", { name, line: t("settings.tnc.state.connected") })),
        }; // ("FM: connected": a name stands before a colon)
  }
  if (line.state === "silent")
    return { ...base, ...word("pill.radio_silent", "pill.radio_named_silent"), tone: "warn", ...whyTitle(silentText(line.since, link.now)) };
  if (line.state === "connecting") return { ...base, ...word("pill.radio_searching", "pill.radio_named_searching"), tone: "warn", ...whyTitle(line.why) };
  return { ...base, ...word("pill.radio_off", "radio.not_connected"), tone: "warn", ...whyTitle(line.why) };
}

/** The one mark of three radios and more: "Radios" while every one is connected (dashed when every one is a Dummy), else the radio in trouble in its words ("20 m: not connected"), or how many are ("Radios: 2 not
 * connected"); its title says each radio with its state; it leads to the first radio in trouble, else to the first box. */
function radiosPill(link: Link, on: readonly PageRadio[], first: PageRadio | undefined): HeaderPill {
  const lines = on.map((radio) => ({ radio, line: lineOf(link, radio) }));
  const said = lines.map(({ radio, line }) => {
    if (line?.state === "connected") return t("radio.line", { name: radio.name, line: t("settings.tnc.state.connected") });
    const mark = radioPill(link, line, "radios", "", radio.name); // (a radio not connected in the words its own mark would have: "Portable: searching…")
    return t(mark.text, mark.textValues);
  });
  const title = whyTitle(said.reduce((all, one) => t("channel.title_join", { first: all, second: one })));
  const trouble = lines.filter(({ line }) => line?.state !== "connected");
  const base = { id: "radios", target: "settings" } as const;
  if (link.connection !== "open")
    return { ...base, text: "pill.radios_waiting", tone: "warn", title: DAEMON_STATES[link.connection].title, focus: radioFocus(first) };
  const [one] = trouble;
  if (one === undefined) return { ...base, text: "pill.radios", tone: on.every((radio) => radio.dummy) ? "dummy" : "ok", ...title, focus: radioFocus(first) };
  if (trouble.length === 1) return { ...radioPill(link, one.line, "radios", radioFocus(one.radio), one.radio.name), ...title };
  return { ...base, text: "pill.radios_trouble", textValues: { n: trouble.length }, tone: "warn", ...title, focus: radioFocus(one.radio) };
}

/** The radio marks: one radio on is the one Radio mark, whichever radio it is (the page names a radio only where there are several); two on are a mark each with its name, each in the state of its own radio; three and
 * more are one Radios mark (at 375 px there is room for about two marks of radios); none for a station the daemon has told has no radio (there is nothing to wait for: the setup's Add radio makes the first). */
function radioPills(link: Link): HeaderPill[] {
  const radios = link.radios;
  if (link.told && radios.length === 0) return [];
  const on = enabledRadios(radios);
  if (on.length >= 3)
    return [
      radiosPill(
        link,
        on,
        radios.find((radio) => !radio.removed),
      ),
    ];
  if (on.length === 2) return on.map((radio) => radioPill(link, lineOf(link, radio), `radio-${radio.id}`, radioFocus(radio), radio.name));
  const one = on[0] ?? radios[0];
  return [radioPill(link, lineOf(link, one), "radio", radioFocus(one), null)];
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

/** RX only while transmitting is off, or while no radio that is on can send (`listening`: each is of a type that only listens; the mark leads to the box of `first`, the first radio that is on), else
 * Beacon off while the beacon is (nothing, when neither). */
function sendingPill(values: Readonly<Record<string, string>>, listening: boolean, first: PageRadio | undefined): HeaderPill | null {
  if (values["station/transmit"] === "false" || listening) {
    const radios = listening && values["station/transmit"] !== "false";
    return {
      id: "rx",
      text: "pill.rx",
      title: radios ? "pill.rx_title_radios" : "pill.rx_title",
      tone: "warn",
      target: "settings",
      focus: radios && first !== undefined ? radioFocus(first) : "set-station-transmit",
    };
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

/** The marks for these settings (key to text) and states; the states are null until the daemon has told. `link` is how the page stands to the daemon and the radio (null: no Daemon or Radio mark); `listening`:
 * no radio that is on can send (lib/radios.ts `listensOnly`). */
export function headerPills(
  values: Readonly<Record<string, string>>,
  gps: GpsState | null,
  igate: IgateState | null,
  update: UpdateInfo | null = null,
  link: Link | null = null,
  map: MapState | null = null,
  listening = false,
): HeaderPill[] {
  const linked = link === null ? [] : [...(link.inApp ? [] : [daemonPill(link.connection)]), ...radioPills(link)];
  const marks = [
    update === null ? null : updatePill(update),
    ...linked,
    sendingPill(values, listening, link === null ? undefined : enabledRadios(link.radios)[0]),
    gpsPill(values, gps),
    internetPill(igate),
    mapPill(map),
  ];
  return marks.filter((mark): mark is HeaderPill => mark !== null);
}
