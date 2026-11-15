// The two radios of before (FM, HF), as the panes of today ask of them and as the settings of before hold them: radio 1 the FM radio, radio 2 the HF radio. Two parts, both of which go when the old wire goes:
// - the views the panes of today read: whether each is switched on, and which of the two a station is messaged on, by the words of the wire of before (`fm` radio 1, `hf` radio 2). The radio a message goes on is
//   what the daemon says (lib/radios.ts `sendingRadio`); a radio of another id, or a daemon that does not say, gets the rule of before: a station heard on FM, or on neither, is messaged on FM, one heard on HF
//   alone on HF. The paths, the route of a station and the requests that carry a path are FM's, since an HF frame goes direct.
// - the rows of the radios out of the settings of before (`pageRows`), for composables/useRadios.ts: against a daemon that tells no topic `radios`, and until it has, radio 1 on unless `fm/enabled` says
//   false and radio 2 off unless `hf/enabled` says true, their lines from the topics `tnc` and `hf`; once the topic is told, its rows, with the Enable of radios 1 and 2 as the settings say it, since the
//   settings are told at once after a save and the topic a moment later, and the panes of today read the settings.
import { RADIO_TYPES } from "@/protocol/lists";
import type { ConfigValues, MessageRow, RadioProblem, RadioRow, StationRow, TncState } from "@/protocol/protocol";
import { pageRadios, radioLabel, sendingRadio, type PageRadio, type RadioId, type RadioType } from "@/lib/radios";

type Values = Readonly<Record<string, string>>;
type HeardOn = Pick<StationRow, "heard_fm" | "heard_hf"> & Partial<Pick<StationRow, "message_radio" | "radio_choice" | "radio_now">>;
type OnItsWay = Pick<MessageRow, "state"> & Partial<Pick<MessageRow, "radio_now">>;

/** The radios, by the word the wire and the settings of before use. */
export type RadioKind = "fm" | "hf";

/** The radios of the settings of before: radio 1 the FM radio, radio 2 the HF radio. */
export const FM_ID: RadioId = 1;
export const HF_ID: RadioId = 2;

/** The setting of before that switches each of the two radios on, and whether it is on when the settings do not say. */
const ENABLE: Record<RadioKind, { id: RadioId; key: string; on: (value: string | undefined) => boolean }> = {
  fm: { id: FM_ID, key: "fm/enabled", on: (value) => value !== "false" },
  hf: { id: HF_ID, key: "hf/enabled", on: (value) => value === "true" },
};

/** The type of radio of a kind that the settings of before name (`tnc/profile`, `hf/profile`), else the first of the kind. */
function typeFor(kind: RadioKind, profile: string): RadioType {
  const ofKind = RADIO_TYPES.filter((entry) => entry.kind === kind);
  const found = ofKind.find((entry) => entry.key === profile) ?? ofKind[0];
  if (found === undefined) throw new Error(`no type of radio of the kind ${kind}`); // (the list holds every kind of before)
  return found;
}

/** Why a radio of before that is on is not connected, from its topic as the Radio group of before reads it. */
function problemOf(kind: RadioKind, link: TncState | null, name: string): RadioProblem {
  if (link?.state === "silent") return { code: "radio.silent", params: { since: link.silent_since ?? "" } };
  if (link !== null && link.searching.length > 0) return { code: "radio.searching", params: {} };
  const reason = link?.modem?.reason ?? "";
  if (kind === "hf" && reason !== "") return { code: `modem.${reason}`, params: {} };
  return { code: "radio.not_connected", params: { name } };
}

const NO_STATS: TncState["stats"] = {
  opens: 0,
  bytes_in: 0,
  bytes_out: 0,
  frames_in: 0,
  packets: 0,
  rejected: 0,
  last_packet: null,
  keepalive_checks: 0,
  watchdog_probes: 0,
  port_reopens: 0,
  digipeated: 0,
  digipeated_at: null,
  digipeat_held: 0,
};

/** What the settings of before choose for a radio of that type: Send on, its path, its digipeater. */
function choicesOf(type: RadioType, values: Values): RadioRow["choices"] {
  return {
    beacon: true,
    path: type.allowed.paths ? (values["beacon/path"] ?? "") : null,
    digipeat: type.allowed.digipeat ? values["digi/enabled"] === "true" : null,
  };
}

/** The line of a radio of before, from its topic: stopped while it is off, connecting before the topic is told. */
const lineOf = (enabled: boolean, link: TncState | null): RadioRow["state"] => (enabled ? (link?.state ?? "connecting") : "stopped");

/** The row of one of the two radios of before, as the daemon would tell it: its type's limits, what it may and can do, its line from its topic (`tnc`, `hf`; null before it is told). */
function flatRow(kind: RadioKind, values: Values, link: TncState | null): RadioRow {
  const type = typeFor(kind, values[kind === "fm" ? "tnc/profile" : "hf/profile"] ?? "");
  const { id, key, on } = ENABLE[kind];
  const enabled = on(values[key]);
  const state = lineOf(enabled, link);
  return {
    id,
    type: type.key,
    kind,
    name: "",
    number: 1,
    enabled,
    position: id,
    removed: false,
    dummy: type.key.startsWith("dummy"),
    state,
    problem: enabled && state !== "connected" ? problemOf(kind, link, radioLabel({ name: "", kind, number: 1 })) : null,
    stats: link?.stats ?? NO_STATS,
    lines: link?.lines ?? [],
    limits: { ...type.limits },
    allowed: { ...type.allowed },
    can: { ...type.can },
    choices: choicesOf(type, values),
    beacon: { last_sent: null, next_due: null, interval_min: 0, problem: null },
    modem: link?.modem ?? null,
    holds: [],
  };
}

/** A row of the topic with the Enable of radio 1 (FM) or 2 (HF) as the settings of before say it (`told`: the settings are told; before, as their defaults say), where they say it; the same row where they say the same. */
function enabledAsSettings(row: RadioRow, values: Values, told: boolean): RadioRow {
  const kind = row.id === FM_ID ? "fm" : row.id === HF_ID ? "hf" : null;
  if (kind === null || row.kind !== kind || row.removed || (told && values[ENABLE[kind].key] === undefined)) return row;
  const enabled = ENABLE[kind].on(values[ENABLE[kind].key]);
  return enabled === row.enabled ? row : { ...row, enabled, state: enabled ? row.state : "stopped", problem: enabled ? row.problem : null };
}

/** The rows of the station's radios by id as text: the topic's once the daemon has told it (`rows`), else the two radios of the settings of before. */
export function pageRows(
  rows: ReadonlyMap<string, RadioRow> | null,
  config: Pick<ConfigValues, "values"> | null,
  tnc: TncState | null,
  hf: TncState | null,
): ReadonlyMap<string, RadioRow> {
  const values = config?.values ?? {};
  if (rows !== null) return new Map([...rows].map(([key, row]) => [key, enabledAsSettings(row, values, config !== null)]));
  return new Map([flatRow("fm", values, tnc), flatRow("hf", values, hf)].map((row) => [String(row.id), row]));
}

/** The two radios of the settings of before, as the page uses them. */
export const flatRadios = (values: Values, tnc: TncState | null = null, hf: TncState | null = null): PageRadio[] =>
  pageRadios(pageRows(null, { values }, tnc, hf), null);

/** Whether the FM radio is on in these settings (before the daemon has told them: on, as the default is). */
export const fmOn = (values: Values): boolean => ENABLE.fm.on(values[ENABLE.fm.key]);

/** Whether the HF radio is on in these settings. */
export const hfOn = (values: Values): boolean => ENABLE.hf.on(values[ENABLE.hf.key]);

/** The word of before of a radio: radio 1 `fm`, radio 2 `hf`; null for any other, which the panes of today do not name. */
const wordOf = (id: RadioId | null): RadioKind | null => (id === FM_ID ? "fm" : id === HF_ID ? "hf" : null);

/** The rule of before of the radio a station is messaged on: the one the operator chose for it (`message_radio`), else HF when it was heard on HF alone, else FM (also for a station nothing was heard of, or none known:
 * null). The channel tags (lib/channels.ts) still go by it. */
export function stationRadio(row: HeardOn | null | undefined): RadioKind {
  if (row?.message_radio === "fm" || row?.message_radio === "hf") return row.message_radio;
  return row != null && row.heard_hf > 0 && row.heard_fm === 0 ? "hf" : "fm";
}

/** The radio a message to a station goes over: the one radio that is on; with both, the one the daemon says (lib/radios.ts `sendingRadio`: `thread` the conversation's messages, `main` the status's main radio, for a
 * station the book does not hold), else, for a radio of another id and against a daemon that does not say, FM unless the station was heard on HF alone. */
export function radioFor(row: HeardOn | null | undefined, values: Values, thread: readonly OnItsWay[] = [], main?: RadioId | null): RadioKind {
  if (!hfOn(values)) return "fm";
  if (!fmOn(values)) return "hf";
  return wordOf(sendingRadio(row, thread, main ?? null)) ?? stationRadio(row);
}

/** Whether the path controls (Route, the path of a request, RF only) are there: the FM radio is on and, for a station (`row` given, null when none is known), it is the radio it is messaged on. */
export const hasPaths = (values: Values, row?: HeardOn | null, thread: readonly OnItsWay[] = [], main?: RadioId | null): boolean =>
  fmOn(values) && (row === undefined || radioFor(row, values, thread, main) === "fm");
