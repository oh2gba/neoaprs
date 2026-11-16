// The radios of the station as the page knows them, in one place: which radios there are, which are on, the email radio and the radio of a call no radio heard, whether there are several, whether
// a radio is named, which radio a station or a message goes on, and what a radio's problem says. Plain functions of what the daemon tells in the topic `radios` (a row for each radio, a removed one kept so that what came by it keeps its name),
// `config.radio_values` and the status; composables/useRadios.ts is the reactive side.
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import { errorReason, type RadioNames } from "@/i18n/errortext";
import { pathCalls } from "@/lib/calls";
import { RADIO_TYPES } from "@/protocol/lists";
import type { ConfigValues, ListPortsCommand, MessageRow, RadioProblem, RadioRow, StationRow, StatusMessage } from "@/protocol/protocol";

/** A radio's id: what every row and command names it by. */
export type RadioId = number;

/** A type of radio, as the daemon describes it (`RADIO_TYPES`): its kind, its words, what it can do and may do, its limits and its own settings. */
export type RadioType = (typeof RADIO_TYPES)[number];

/** The key of a type of radio: what a radio's `type` is. */
type RadioTypeKey = RadioType["key"];

type Values = Readonly<Record<string, string>>;

/** One radio of the station, as the page uses it. The same object stays while none of its own fields changes, so that a pane that draws it is not drawn again for each count of its line. */
export interface PageRadio {
  id: RadioId;
  kind: RadioRow["kind"];
  type: RadioTypeKey;
  /** what the page calls it: the name typed, else its kind's word and its number in the kind ("HF 2") */
  name: string;
  /** its name is its kind's word alone ("FM", "HF"): no name typed and the first of its kind. Its own field, so that a tag that names the radio does not read `row` (which follows the counts) */
  plain: boolean;
  /** it is on: its Enable is ticked and it is not removed */
  enabled: boolean;
  removed: boolean;
  dummy: boolean;
  /** its frames may carry a path of digipeaters (its type allows it) */
  carriesPath: boolean;
  /** its own settings in force by the key of the field (`port`, `sound_card`), from `config.radio_values` */
  settings: Readonly<Record<string, string>>;
  /** its line: `stopped` while it is off or removed */
  state: RadioRow["state"];
  /** why it is not connected, while it is on and not connected; null otherwise (problemText says it) */
  problem: RadioProblem | null;
  /** its line is up: what a command that goes over it waits for */
  connected: boolean;
  /** its row of the topic as the daemon told it last (its counts, its lines, its beacon, what its type can and may do) */
  readonly row: RadioRow;
}

/** The word of each kind. */
export const KIND_WORDS: Record<RadioRow["kind"], MessageId> = { fm: "channel.fm", hf: "channel.hf", lora: "channel.lora" };

/** What the page calls a radio: the name typed, else the word of its kind, with its number in the kind from the second on ("HF", "HF 2"). */
export function radioLabel(row: Pick<RadioRow, "name" | "kind" | "number">, words: typeof t = t): string {
  if (row.name !== "") return row.name;
  const word = words(KIND_WORDS[row.kind]);
  return row.number > 1 ? `${word} ${row.number}` : word;
}

/** The id of a page element made from a setting's key: every "/" a "-" ("radio-3-port"). */
export const fieldId = (key: string): string => key.replaceAll("/", "-");

/** The type of a radio, as `RADIO_TYPES` describes it; undefined for a key the page does not know. */
export const typeOf = (radio: { type: string }): RadioType | undefined => RADIO_TYPES.find((entry) => entry.key === radio.type);

/** The words of the state of a radio's line, as the Radio group says them. */
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

/** What a radio's problem says to the operator: the words of its line's state, else (a device another holds, RX only, a beacon not sent) the sentence of its refusal, and "Not connected" where the catalogue has none.
 * `radios`: the page's, by which the radio holding a device is said in the page's words. */
export function problemText(problem: RadioProblem, words: typeof t = t, radios?: RadioNames): string {
  const id = PROBLEM_WORDS[problem.code];
  if (id !== undefined) return words(id, problem.params);
  return errorReason({ code: problem.code, params: problem.params, cmd: "", key: null, text: "" }, radios, () => words("settings.tnc.not_connected"));
}

/** A radio's own settings out of `radio_values`, by the key of the field. */
function settingsOf(id: RadioId, radioValues: Values): Record<string, string> {
  const prefix = `radio/${id}/`;
  return Object.fromEntries(Object.entries(radioValues).flatMap(([key, value]) => (key.startsWith(prefix) ? [[key.slice(prefix.length), value]] : [])));
}

/** A radio of the topic. `live` gives its row as the daemon tells it now, so that `row` follows the counts while the radio stays the same object; without it, `row` is the one given. */
export function pageRadio(row: RadioRow, radioValues: Values = {}, live?: () => RadioRow | undefined): PageRadio {
  const enabled = row.enabled && !row.removed;
  return {
    id: row.id,
    kind: row.kind,
    type: row.type as RadioTypeKey, // (the daemon's rows and RADIO_TYPES are made from the one registry of types)
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

/** Every radio of the topic, removed ones too, in the order of their boxes (by position, then by id). */
export function pageRadios(
  rows: ReadonlyMap<string, RadioRow>,
  config: Pick<ConfigValues, "radio_values"> | null,
  live?: (id: RadioId) => RadioRow | undefined,
): PageRadio[] {
  const radioValues = config?.radio_values ?? {};
  return [...rows.values()].sort((a, b) => a.position - b.position || a.id - b.id).map((row) => pageRadio(row, radioValues, live && (() => live(row.id))));
}

/** Whether two makings of a radio say the same of it (all but its row's counts, lines and beacon, which `row` gives as they are). */
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

/** The radios that are on, in the order of their boxes. */
export const enabledRadios = (radios: readonly PageRadio[]): PageRadio[] => radios.filter((radio) => radio.enabled);

/** The radios that are on and can send, in the order of their boxes: a radio of a type that only listens (`can.transmit` false) is never one, nor offered where a radio is chosen to send on. */
export const senders = (radios: readonly PageRadio[]): PageRadio[] => enabledRadios(radios).filter((radio) => typeOf(radio)?.can.transmit !== false);

/** Whether some radio is on and none of those can send (each of a type that only listens): nothing is sent, as with RX only ticked. False from a daemon of the wire of before, which tells no topic `radios`. */
export function listensOnly(rows: ReadonlyMap<string, RadioRow> | null): boolean {
  const on = [...(rows?.values() ?? [])].filter((row) => row.enabled && !row.removed);
  return on.length > 0 && on.every((row) => !row.can.transmit);
}

/** The path a radio takes while its own path is empty (what its Recommended choice says): the one its kind's types recommend (`recommended_path`: LoRa WIDE1-1, as neoaprs/radiotypes `recommended_path`), else
 * `symbolPath`, the recommended path of the station's symbol. */
export function recommendedFor(radio: Pick<PageRadio, "kind">, symbolPath: string): string {
  return RADIO_TYPES.find((type) => type.kind === radio.kind && type.recommended_path !== "")?.recommended_path || symbolPath;
}

/** The path our frames take on a radio, as the daemon gives it (neoaprs/config.py `path_calls`): its own path (`radio/<id>/path`); empty, the path its kind recommends (LoRa WIDE1-1), else `symbolPath`, the
 * recommended path of the station's symbol; "" for DIRECT. The calls separated by commas: the placeholder of a Path field that belongs to that radio. */
export function radioPath(radio: Pick<PageRadio, "kind" | "settings">, symbolPath: string): string {
  const text = radio.settings["path"] ?? "";
  return (pathCalls(text, recommendedFor(radio, symbolPath)) ?? [text]).join(",");
}

/** The one path these radios share, of those that may carry one (`pathOf` gives each one's); null while they go by different paths, and while none of them carries a path. */
export function sharedPath(radios: readonly PageRadio[], pathOf: (radio: PageRadio) => string): string | null {
  const paths = new Set(radios.filter((radio) => radio.carriesPath).map(pathOf));
  return paths.size === 1 ? ([...paths][0] ?? null) : null;
}

/** Whether the radio of that id is there and on. */
export const isOn = (radios: readonly PageRadio[], id: RadioId): boolean => radios.some((radio) => radio.id === id && radio.enabled);

/** Whether a radio is named where something of it is shown: where more than one radio is on, and always for one that is not on (off, removed, or not known), so that what came by it keeps its name. */
export const isNamed = (radios: readonly PageRadio[], id: RadioId): boolean => enabledRadios(radios).length > 1 || !isOn(radios, id);

/** The radio of a message to a call no radio heard (and of a text to CQ, ALL, QST): the one the daemon's status names (`unheard_radio`, none while no radio can send), else, before the status has come, the first radio
 * that is on and can send, in the order of the boxes. Route shows it as what "Automatic" gives. */
export function unheardRadio(radios: readonly PageRadio[], status: Partial<Pick<StatusMessage, "unheard_radio">> | null): PageRadio | null {
  const named = status?.unheard_radio;
  if (named === null) return null;
  const on = senders(radios);
  return (named === undefined ? undefined : on.find((radio) => radio.id === named)) ?? on[0] ?? null;
}

/** The email radio, of any kind: the one the daemon's status names (`email_radio`: the operator's choice in the Email tab while it is on; none while no radio can send), else, before the status has come, the first
 * radio that can send, in the order of the boxes. */
export function emailRadio(radios: readonly PageRadio[], status: Partial<Pick<StatusMessage, "email_radio">> | null): PageRadio | null {
  const named = status?.email_radio;
  if (named === null) return null;
  const on = senders(radios);
  return (named === undefined ? undefined : on.find((radio) => radio.id === named)) ?? on[0] ?? null;
}

type ToStation = Partial<Pick<StationRow, "radio_choice" | "radio_now">>;
type OnItsWay = Pick<MessageRow, "state"> & Partial<Pick<MessageRow, "radio_now">>;

/** The radio a message to a station goes on, as the daemon says it (plan rule 3.2), in this order:
 * - the operator's choice for the station while it is in force: it holds also for a message on its way, from its next attempt, and the station's `radio_now` is then the choice;
 * - a message of ours on its way to it (`thread`, the conversation's messages): the one being sent, else one that waits its turn, which keeps the radio of its first attempt;
 * - the station's radio now;
 * - for a call the book does not hold (`row` null), the radio of a call no radio heard (`unheard`: the daemon's `status.unheard_radio`).
 * Null where the daemon says there is none, and against a daemon that does not say (a row without `radio_now`). */
export function sendingRadio(row: ToStation | null | undefined, thread: readonly OnItsWay[] = [], unheard: RadioId | null = null): RadioId | null {
  if (row?.radio_choice != null && row.radio_now != null) return row.radio_now;
  const ours = (state: MessageRow["state"]) => thread.find((message) => message.state === state && message.radio_now != null)?.radio_now; // (only a message of ours is sending or queued)
  return ours("sending") ?? ours("queued") ?? (row != null ? (row.radio_now ?? null) : unheard);
}

/** The radio of a message: the one its next attempt goes on while it is on its way, else the one it came or went on (`radio_id`); null for none (an internet message, one never sent). */
export const messageRadio = (row: Partial<Pick<MessageRow, "radio_now" | "radio_id">>): RadioId | null => row.radio_now ?? row.radio_id ?? null;

/** The asks for the ports: one for each radio that is on and whose type has a sound card (the cards and the keying's proposal come only with a radio named), else the ports alone. The page keeps the latest answer, so
 * an ask that names no radio would leave such a radio's box without its cards. */
export function portsAsks(rows: Iterable<RadioRow>): ListPortsCommand[] {
  const named = [...rows].filter((row) => row.enabled && !row.removed && row.can.tune).map((row): ListPortsCommand => ({ cmd: "list_ports", radio: row.id }));
  return named.length > 0 ? named : [{ cmd: "list_ports" }];
}
