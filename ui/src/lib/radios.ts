// Radio logic of the page: which radios exist, which are on and can send, which radio a station or
// message goes on, and how a radio's problem is worded. Plain functions of the daemon's `radios`
// topic, `config.radio_values` and the status; composables/useRadios.ts is the reactive side.
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import { errorReason, type RadioNames } from "@/i18n/errortext";
import { pathCalls } from "@/lib/calls";
import { RADIO_TYPES } from "@/protocol/lists";
import type {
  ConfigValues,
  ListPortsCommand,
  MessageRow,
  RadioProblem,
  RadioRow,
  StationRow,
  StatusMessage,
} from "@/protocol/protocol";

/** A radio's id: what every row and command names it by. */
export type RadioId = number;

/**
 * A radio type as the daemon describes it (`RADIO_TYPES`): kind, labels, capabilities, limits and
 * settings.
 */
export type RadioType = (typeof RADIO_TYPES)[number];

/** The key of a type of radio: what a radio's `type` is. */
type RadioTypeKey = RadioType["key"];

type Values = Readonly<Record<string, string>>;

/** One radio as the page uses it. The object stays the same while its own fields do not change. */
export interface PageRadio {
  id: RadioId;
  kind: RadioRow["kind"];
  type: RadioTypeKey;
  /** Display name: the typed name, else the kind's word and its number ("HF 2"). */
  name: string;
  /**
   * The name is the kind's word alone ("FM", "HF"); a field of its own so that tags do not read
   * `row`.
   */
  plain: boolean;
  /** On: enabled and not removed. */
  enabled: boolean;
  removed: boolean;
  dummy: boolean;
  /** Frames may carry a digipeater path (the type allows it). */
  carriesPath: boolean;
  /** Own settings by field key (`port`, `sound_card`), from `config.radio_values`. */
  settings: Readonly<Record<string, string>>;
  /** Line state; `stopped` while off or removed. */
  state: RadioRow["state"];
  /** Why it is not connected while on; null otherwise (see problemText). */
  problem: RadioProblem | null;
  /** The line is up: what a command sent over this radio waits for. */
  connected: boolean;
  /** The daemon's last row for this radio (counts, lines, beacon, capabilities). */
  readonly row: RadioRow;
}

export const KIND_WORDS: Record<RadioRow["kind"], MessageId> = {
  fm: "channel.fm",
  hf: "channel.hf",
  lora: "channel.lora",
};

/** Display name: the typed name, else the kind's word, numbered from the second ("HF", "HF 2"). */
export function radioLabel(row: Pick<RadioRow, "name" | "kind" | "number">, words: typeof t = t): string {
  if (row.name !== "") return row.name;
  const word = words(KIND_WORDS[row.kind]);
  return row.number > 1 ? `${word} ${row.number}` : word;
}

/** An element id made from a setting key, with "/" replaced by "-" ("radio-3-port"). */
export const fieldId = (key: string): string => key.replaceAll("/", "-");

/** The type for a key, or undefined if the page does not know it. */
export const typeOf = (radio: { type: string }): RadioType | undefined =>
  RADIO_TYPES.find((entry) => entry.key === radio.type);

/** Wording for each line state, as the Radio group shows it. */
const PROBLEM_WORDS: Partial<Record<RadioProblem["code"], MessageId>> = {
  "radio.not_connected": "settings.tnc.not_connected",
  "radio.searching": "settings.tnc.searching",
  "radio.silent": "settings.tnc.state.silent",
  "radio.text_lines": "settings.tnc.text_lines",
  "modem.not_installed": "settings.tnc.hf.not_installed",
  "modem.stopped": "settings.tnc.hf.stopped",
  "modem.network": "settings.tnc.hf.network",
  "modem.no_port": "settings.tnc.hf.no_port",
  "modem.not_started": "settings.tnc.hf.not_started",
  "modem.sound_card": "settings.tnc.hf.sound_card",
  "modem.keying": "settings.tnc.hf.keying",
};

/**
 * What a radio's problem says to the operator: the line state's words, else (device held by another
 * radio, RX only, beacon not sent) the refusal's sentence, else "Not connected". `radios` names the
 * radio holding a device.
 */
export function problemText(problem: RadioProblem, words: typeof t = t, radios?: RadioNames): string {
  const id = PROBLEM_WORDS[problem.code];
  if (id !== undefined) return words(id, problem.params);
  return errorReason({ code: problem.code, params: problem.params, cmd: "", key: null, text: "" }, radios, () =>
    words("settings.tnc.not_connected"),
  );
}

/** A radio's own settings from `radio_values`, by field key. */
function settingsOf(id: RadioId, radioValues: Values): Record<string, string> {
  const prefix = `radio/${id}/`;
  return Object.fromEntries(
    Object.entries(radioValues).flatMap(([key, value]) =>
      key.startsWith(prefix) ? [[key.slice(prefix.length), value]] : [],
    ),
  );
}

/**
 * Build a radio from a topic row. With `live`, `row` follows the latest row while the radio object
 * stays the same.
 */
export function pageRadio(row: RadioRow, radioValues: Values = {}, live?: () => RadioRow | undefined): PageRadio {
  const enabled = row.enabled && !row.removed;
  return {
    id: row.id,
    kind: row.kind,
    type: row.type as RadioTypeKey,
    name: radioLabel(row),
    plain: row.name === "" && row.number === 1,
    enabled,
    removed: row.removed,
    dummy: row.dummy,
    carriesPath: row.allowed.paths,
    settings: settingsOf(row.id, radioValues),
    state: row.state,
    problem: row.problem,
    connected: enabled && row.state === "connected",
    get row() {
      return live?.() ?? row;
    },
  };
}

/** Every radio of the topic, removed ones included, ordered by position, then id. */
export function pageRadios(
  rows: ReadonlyMap<string, RadioRow>,
  config: Pick<ConfigValues, "radio_values"> | null,
  live?: (id: RadioId) => RadioRow | undefined,
): PageRadio[] {
  const radioValues = config?.radio_values ?? {};
  return [...rows.values()]
    .sort((a, b) => a.position - b.position || a.id - b.id)
    .map((row) => pageRadio(row, radioValues, live && (() => live(row.id))));
}

/** Whether two builds of a radio say the same (ignoring `row`'s counts, lines and beacon). */
export function sameRadio(a: PageRadio, b: PageRadio): boolean {
  const own = (radio: PageRadio) => [
    radio.id,
    radio.kind,
    radio.type,
    radio.name,
    radio.plain,
    radio.enabled,
    radio.removed,
    radio.dummy,
    radio.carriesPath,
    radio.state,
    radio.connected,
  ];
  return (
    own(a).every((value, i) => value === own(b)[i]) &&
    JSON.stringify(a.problem) === JSON.stringify(b.problem) &&
    JSON.stringify(Object.entries(a.settings)) === JSON.stringify(Object.entries(b.settings))
  );
}

/** The radios that are on, in box order. */
export const enabledRadios = (radios: readonly PageRadio[]): PageRadio[] => radios.filter((radio) => radio.enabled);

/**
 * The radios that are on and can send, in box order. Listen-only types (`can.transmit` false) are
 * never included.
 */
export const senders = (radios: readonly PageRadio[]): PageRadio[] =>
  enabledRadios(radios).filter((radio) => typeOf(radio)?.can.transmit !== false);

/**
 * True when some radio is on but none can send, so nothing is sent (as with RX only). False for a
 * daemon that sends no `radios` topic.
 */
export function listensOnly(rows: ReadonlyMap<string, RadioRow> | null): boolean {
  const on = [...(rows?.values() ?? [])].filter((row) => row.enabled && !row.removed);
  return on.length > 0 && on.every((row) => !row.can.transmit);
}

/**
 * The path a radio uses while its own is empty: the kind's recommended path (`recommended_path`,
 * LoRa WIDE1-1), else `symbolPath`, the recommended path of the station's symbol.
 */
export function recommendedFor(radio: Pick<PageRadio, "kind">, symbolPath: string): string {
  return (
    RADIO_TYPES.find((type) => type.kind === radio.kind && type.recommended_path !== "")?.recommended_path || symbolPath
  );
}

/**
 * The path our frames take on a radio, as the daemon computes it (neoaprs/config.py `path_calls`):
 * the radio's own path, else the kind's recommended path, else `symbolPath`; "" for DIRECT.
 * Comma-separated.
 */
export function radioPath(radio: Pick<PageRadio, "kind" | "settings">, symbolPath: string): string {
  const text = radio.settings["path"] ?? "";
  return (pathCalls(text, recommendedFor(radio, symbolPath)) ?? [text]).join(",");
}

/** The path these radios share, or null when they differ or none carries a path. */
export function sharedPath(radios: readonly PageRadio[], pathOf: (radio: PageRadio) => string): string | null {
  const paths = new Set(radios.filter((radio) => radio.carriesPath).map(pathOf));
  return paths.size === 1 ? ([...paths][0] ?? null) : null;
}

/** Whether the radio with that id exists and is on. */
export const isOn = (radios: readonly PageRadio[], id: RadioId): boolean =>
  radios.some((radio) => radio.id === id && radio.enabled);

/** Whether a radio is named in displays: when several are on, and always for one that is not on. */
export const isNamed = (radios: readonly PageRadio[], id: RadioId): boolean =>
  enabledRadios(radios).length > 1 || !isOn(radios, id);

/**
 * The radio for a message to a call no radio heard, or to CQ, ALL, QST: the status's
 * `unheard_radio`, else the first radio that is on and can send.
 */
export function unheardRadio(
  radios: readonly PageRadio[],
  status: Partial<Pick<StatusMessage, "unheard_radio">> | null,
): PageRadio | null {
  const named = status?.unheard_radio;
  if (named === null) return null;
  const on = senders(radios);
  return (named === undefined ? undefined : on.find((radio) => radio.id === named)) ?? on[0] ?? null;
}

/** The email radio: the status's `email_radio`, else the first radio that can send. */
export function emailRadio(
  radios: readonly PageRadio[],
  status: Partial<Pick<StatusMessage, "email_radio">> | null,
): PageRadio | null {
  const named = status?.email_radio;
  if (named === null) return null;
  const on = senders(radios);
  return (named === undefined ? undefined : on.find((radio) => radio.id === named)) ?? on[0] ?? null;
}

type ToStation = Partial<Pick<StationRow, "radio_choice" | "radio_now">>;
type OnItsWay = Pick<MessageRow, "state"> & Partial<Pick<MessageRow, "radio_now">>;

/**
 * The radio a message to a station goes on, as the daemon decides it (plan rule 3.2), in this
 * order:
 * - the operator's choice for the station while it is in force;
 * - a message of ours on its way to it (`thread`): the one being sent, else the one queued;
 * - the station's `radio_now`;
 * - for a call not in the book (`row` null), the unheard radio (`status.unheard_radio`). Null where
 *   the daemon says there is none, or does not say (no `radio_now`).
 */
export function sendingRadio(
  row: ToStation | null | undefined,
  thread: readonly OnItsWay[] = [],
  unheard: RadioId | null = null,
): RadioId | null {
  if (row?.radio_choice != null && row.radio_now != null) return row.radio_now;
  const ours = (state: MessageRow["state"]) =>
    thread.find((message) => message.state === state && message.radio_now != null)?.radio_now;
  return ours("sending") ?? ours("queued") ?? (row != null ? (row.radio_now ?? null) : unheard);
}

/** A message's radio: its next attempt's radio while on its way, else `radio_id`; null if none. */
export const messageRadio = (row: Partial<Pick<MessageRow, "radio_now" | "radio_id">>): RadioId | null =>
  row.radio_now ?? row.radio_id ?? null;

/**
 * The port asks: one for each radio that is on and has a sound card, else a plain ask. The page
 * keeps only the latest answer, so an ask naming no radio would leave such a radio without its
 * cards.
 */
export function portsAsks(rows: Iterable<RadioRow>): ListPortsCommand[] {
  const named = [...rows]
    .filter((row) => row.enabled && !row.removed && row.can.tune)
    .map((row): ListPortsCommand => ({ cmd: "list_ports", radio: row.id }));
  return named.length > 0 ? named : [{ cmd: "list_ports" }];
}
