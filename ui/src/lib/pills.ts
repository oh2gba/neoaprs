// The marks at the top right of the header, before the message count. Each has a short hover title
// and the place where it is set. The order is also the fold order on a narrow screen (the last
// folds first): Update, Daemon (browser only), radios, Beacon off, GPS, Internet, Map. The RX only
// switch after the count is lib/rxswitch.ts. They are plain functions of the settings, the radios
// and the states the daemon has reported.
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

/** Where a mark leads: a Settings tab (Radio, Internet) or the My station tab (beacon, GPS). */
export type PillTarget = "settings" | "beacon";

export interface HeaderPill {
  id: "update" | "daemon" | "radio" | `radio-${RadioId}` | "radios" | "beacon_off" | "internet" | "gps" | "map";
  text: MessageId;
  textValues?: Params;
  title: MessageId;
  /** Values for the title text (the newer version). */
  titleValues?: Params;
  tone: TagTone;
  /** Where a click leads; null for a mark that only informs (the Daemon mark). */
  target: PillTarget | null;
  /**
   * Id of the control the mark leads to; its group is brought into view and flashed
   * (lib/attention.ts).
   */
  focus: string;
}

/**
 * What the page knows of the link to the daemon and the radios: the socket, the radios (useRadios
 * `all`), whether the daemon has reported them (`told`; a station with no radio has none to wait
 * for), the time now, and whether this is the desktop app (no Daemon mark).
 */
export interface Link {
  connection: Connection;
  now: number;
  inApp: boolean;
  radios: readonly PageRadio[];
  told: boolean;
}

/**
 * Daemon mark words per socket state; a radio's mark says the same while the socket is not open.
 */
export const DAEMON_STATES = {
  open: { text: "pill.daemon", title: "pill.daemon_title", tone: "ok" },
  connecting: { text: "pill.daemon_connecting", title: "pill.daemon_connecting_title", tone: "warn" },
  closed: { text: "pill.daemon_offline", title: "pill.daemon_offline_title", tone: "bad" },
} as const;

/** The Daemon mark: the state of the page's socket. */
function daemonPill(connection: Connection): HeaderPill {
  return { id: "daemon", ...DAEMON_STATES[connection], target: null, focus: "" };
}

/**
 * A radio's line as a mark shows it: state, Dummy or not, silence time, reason; null while unknown.
 */
interface Line {
  state: RadioRow["state"];
  dummy: boolean;
  since: string | null;
  why: string;
}

/**
 * Why a radio is not connected: its coded problem (lib/radios.ts `problemText`), searching while
 * its line opens, else its state. Never the daemon's own text, which names ports and devices.
 */
function whyOf(state: RadioRow["state"], radio: PageRadio | undefined, radios: readonly PageRadio[] = []): string {
  const problem = radio?.problem ?? null;
  if (state === "connecting" && (problem === null || problem.code === "radio.not_connected"))
    return t("settings.tnc.searching");
  return problem === null
    ? t(`settings.tnc.state.${state}`)
    : problemText(problem, t, { byId: (id) => radios.find((one) => one.id === id) });
}

/** The line of a radio from its row of the topic `radios`. */
function lineOfRow(radio: PageRadio, radios: readonly PageRadio[]): Line {
  const since = radio.problem?.code === "radio.silent" ? String(radio.problem.params["since"] ?? "") : "";
  return {
    state: radio.state,
    dummy: radio.dummy,
    since: since === "" ? null : since,
    why: whyOf(radio.state, radio, radios),
  };
}

/**
 * The line of a radio from its row; unknown (waiting) while the socket is not open, and for no
 * radio.
 */
function lineOf(link: Link, radio: PageRadio | undefined): Line | null {
  return link.connection !== "open" || radio === undefined ? null : lineOfRow(radio, link.radios);
}

/**
 * The control a radio's mark leads to in its Settings → Radio box: its Enable, or Add radio when
 * none.
 */
export function radioFocus(radio: Pick<PageRadio, "id"> | undefined): string {
  return radio === undefined ? "set-radio-add" : enableId(radio);
}

/** The title "{why}. Settings → Radio"; the reason has no stop of its own. */
const whyTitle = (text: string) =>
  ({ title: "pill.radio_why_title", titleValues: { why: text.replace(/[.…。]+$/u, "") } }) as const;

/**
 * The mark of a radio in the state of its line. `name` is its short name when several marks show.
 */
function radioPill(
  link: Link,
  line: Line | null,
  id: HeaderPill["id"],
  focus: string,
  name: string | null,
): HeaderPill {
  const base = { id, target: "settings", focus } as const;
  // `name` also fills the shared words, e.g. "{name}: not connected"
  const values = name === null ? undefined : { radio: name, name };
  const word = (plain: MessageId, withName: MessageId) =>
    ({ text: name === null ? plain : withName, textValues: values }) as const;
  if (line === null) {
    // socket away: use the Daemon mark's words
    const title =
      link.connection === "open"
        ? whyTitle(t("pill.radio_waiting_why"))
        : { title: DAEMON_STATES[link.connection].title };
    return { ...base, ...word("pill.radio_waiting", "pill.radio_named_waiting"), tone: "warn", ...title };
  }
  if (line.state === "connected") {
    if (line.dummy)
      return { ...base, ...word("pill.radio", "pill.radio_named"), title: "pill.radio_dummy_title", tone: "dummy" };
    return name === null
      ? { ...base, text: "pill.radio", title: "pill.radio_title", tone: "ok" }
      : {
          ...base,
          text: "pill.radio_named",
          textValues: values,
          tone: "ok",
          ...whyTitle(t("radio.line", { name, line: t("settings.tnc.state.connected") })),
        };
  }
  if (line.state === "silent")
    return {
      ...base,
      ...word("pill.radio_silent", "pill.radio_named_silent"),
      tone: "warn",
      ...whyTitle(silentText(line.since, link.now)),
    };
  if (line.state === "connecting")
    return {
      ...base,
      ...word("pill.radio_searching", "pill.radio_named_searching"),
      tone: "warn",
      ...whyTitle(line.why),
    };
  return { ...base, ...word("pill.radio_off", "radio.not_connected"), tone: "warn", ...whyTitle(line.why) };
}

/**
 * The one mark for three or more radios: "Radios" while all are connected (dashed when all are
 * Dummies), else the radio in trouble ("20 m: not connected") or the count ("Radios: 2 not
 * connected"). Its title lists each radio's state; it leads to the first radio in trouble, else the
 * first box.
 */
function radiosPill(link: Link, on: readonly PageRadio[], first: PageRadio | undefined): HeaderPill {
  const lines = on.map((radio) => ({ radio, line: lineOf(link, radio) }));
  const said = lines.map(({ radio, line }) => {
    if (line?.state === "connected")
      return t("radio.line", { name: radio.name, line: t("settings.tnc.state.connected") });
    // the words its own mark would use: "Portable: searching…"
    const mark = radioPill(link, line, "radios", "", radio.name);
    return t(mark.text, mark.textValues);
  });
  const title = whyTitle(said.reduce((all, one) => t("channel.title_join", { first: all, second: one })));
  const trouble = lines.filter(({ line }) => line?.state !== "connected");
  const base = { id: "radios", target: "settings" } as const;
  if (link.connection !== "open")
    return {
      ...base,
      text: "pill.radios_waiting",
      tone: "warn",
      title: DAEMON_STATES[link.connection].title,
      focus: radioFocus(first),
    };
  const [one] = trouble;
  if (one === undefined)
    return {
      ...base,
      text: "pill.radios",
      tone: on.every((radio) => radio.dummy) ? "dummy" : "ok",
      ...title,
      focus: radioFocus(first),
    };
  if (trouble.length === 1)
    return { ...radioPill(link, one.line, "radios", radioFocus(one.radio), one.radio.name), ...title };
  return {
    ...base,
    text: "pill.radios_trouble",
    textValues: { n: trouble.length },
    tone: "warn",
    ...title,
    focus: radioFocus(one.radio),
  };
}

/**
 * The radio marks: one radio gives the Radio mark; two give a mark each with its name; three or
 * more give one Radios mark. None when the daemon has reported that the station has no radio.
 */
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
  if (on.length === 2)
    return on.map((radio) => radioPill(link, lineOf(link, radio), `radio-${radio.id}`, radioFocus(radio), radio.name));
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

/** Beacon off while the beacon is, whatever RX only is. */
function beaconPill(values: Readonly<Record<string, string>>): HeaderPill | null {
  if (!beaconOff(values)) return null;
  return {
    id: "beacon_off",
    text: "pill.beacon_off",
    title: "pill.beacon_off_title",
    tone: "neutral",
    target: "beacon",
    focus: "set-beacon-interval_min",
  };
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
  const up =
    igate !== null &&
    igate.enabled &&
    (igate.state === "connected" || igate.state === "listening" || igate.state === "unverified");
  return up
    ? {
        id: "internet",
        text: "pill.internet",
        title: "pill.internet_title",
        tone: "info",
        target: "settings",
        focus: "set-igate-enabled",
      }
    : null;
}

/**
 * The Map mark while the detailed map downloads (Settings → Map or after the setup): percent when
 * known.
 */
function mapPill(map: MapState | null): HeaderPill | null {
  if (map === null || map.state !== "downloading") return null;
  const base = {
    id: "map",
    title: "pill.map_title",
    tone: "info",
    target: "settings",
    focus: "set-map-fetch",
  } as const;
  return map.percent === null
    ? { ...base, text: "pill.map_working" }
    : { ...base, text: "pill.map", textValues: { percent: map.percent } };
}

/**
 * The marks for these settings (key to text) and states, null until the daemon has reported. `link`
 * is the page's standing to daemon and radios (null: no Daemon or Radio mark).
 */
export function headerPills(
  values: Readonly<Record<string, string>>,
  gps: GpsState | null,
  igate: IgateState | null,
  update: UpdateInfo | null = null,
  link: Link | null = null,
  map: MapState | null = null,
): HeaderPill[] {
  const linked = link === null ? [] : [...(link.inApp ? [] : [daemonPill(link.connection)]), ...radioPills(link)];
  const marks = [
    update === null ? null : updatePill(update),
    ...linked,
    beaconPill(values),
    gpsPill(values, gps),
    internetPill(igate),
    mapPill(map),
  ];
  return marks.filter((mark): mark is HeaderPill => mark !== null);
}
