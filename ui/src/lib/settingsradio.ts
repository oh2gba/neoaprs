// Which settings are there for the radios in use (the beacon's interval while a radio is on, Travelling while one that is on has SmartBeaconing), and the keys of a radio's box in the Radio group: each radio by its
// own `radio/<id>/<key>` of `config.radio_values`, its type's fields (RADIO_TYPES).
import { inject, shallowRef, type InjectionKey, type ShallowRef } from "vue";
import { hasMessage, t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import { enabledRadios, fieldId, KIND_WORDS as KIND_NAMES, radioLabel, typeOf, type PageRadio, type RadioType } from "@/lib/radios";
import type { Choice } from "@/lib/settingchoices";
import type { PortsMessage, RadioRow } from "@/protocol/protocol";
import { RADIO_STATION_KEYS, RADIO_TYPES } from "@/protocol/lists";

/** Whether a station setting is a field of the form: the access key while the daemon lets the network in (`network`) and has made one. The port the search found last is no field: the port's own control says it. */
export function shownFor(key: string, network = true): boolean {
  if (key === "web/key" || key === "web/https") return network;
  return key !== "serial/last_port";
}

/** What a moving station travels as: SmartBeaconing's preset. (The GPS itself, the Position choice and where the receiver is, stay: a station on HF alone can move, with the timed beacon.) */
const MOVING_KEYS = ["beacon/travel"];

/** The key the Beacon group's Path fold is drawn by: the paths it holds are the radios' own (`radio/<id>/path`). */
const PATH_FOLD = "beacon/path";

/** Whether a setting is there for the radios that are on: the one Beacon choice while any radio is, Travelling while one that is on has SmartBeaconing, and the Path fold while one that is on may carry a path. */
export function shownByRadios(key: string, radios: readonly PageRadio[]): boolean {
  const on = enabledRadios(radios);
  if (key === "beacon/interval_min") return on.length > 0;
  if (MOVING_KEYS.includes(key)) return on.some((radio) => radio.row.allowed.smart_beacon);
  if (key === PATH_FOLD) return on.some((radio) => radio.carriesPath);
  return true;
}

/** A radio's own setting (`radio/3/port`) or a station setting of the radios (`station/main_radio`): the places of the radios show them (the boxes of the Radio group, the main radio, the Digipeater group), not the groups of the form. */
export const isRadioKey = (key: string): boolean => key.startsWith("radio/") || (RADIO_STATION_KEYS as readonly string[]).includes(key);

/** The radio and the field of a radio's own setting: `radio/3/port` is radio 3's `port`; null for any other key. */
export function radioFieldOf(key: string): { id: number; field: string } | null {
  const found = /^radio\/(\d+)\/([a-z_]+)$/.exec(key);
  return found === null ? null : { id: Number(found[1]), field: found[2] ?? "" };
}

/** The field of a radio a key is: `radio/3/port` is `port`; the key itself for one that is none. */
export const fieldOfKey = (key: string): string => radioFieldOf(key)?.field ?? key;

/** The key of lib/settings.ts FIELDS that a radio's field is described and checked by (`port` by `serial/port`), since the words and the rules of a port are the same for every radio. */
const FIELD_WORDS: Readonly<Record<string, string>> = {
  port: "serial/port",
  baud: "serial/baud",
  tcp_host: "tcp/host",
  tcp_port: "tcp/port",
  digipeat: "digi/enabled",
  path: "beacon/path",
  sound_card: "mercury/sound_card",
  keying: "mercury/keying",
  tx_gain_db: "mercury/tx_gain_db",
};

/** Where a kind's field has words of its own: a LoRa board's address is on the network, with no default and none of Direwolf's ports (the rules stay the field's: `flatKeyOf` without the kind). */
const KIND_WORDS: Readonly<Partial<Record<PageRadio["kind"], Readonly<Record<string, string>>>>> = { lora: { tcp_host: "lora/host", tcp_port: "lora/port" } };

/** The key a radio's field takes its words and its rules from (`port` is `serial/port`), its kind's own words where it has them; null for a field that has none. */
export const flatKeyOf = (field: string, kind?: PageRadio["kind"]): string | null =>
  (kind === undefined ? undefined : KIND_WORDS[kind]?.[field]) ?? FIELD_WORDS[field] ?? null;

/** The fields of a radio that are shown elsewhere than behind its status: the beacon's and the status's Send on and its path (My station), its digipeater (the Digipeater group) and the transmit level, which is a row of its own. */
const ELSEWHERE = ["beacon", "status", "path", "digipeat", "tx_gain_db"];

/** The keys behind the status of a radio: its type's fields there (the host and the TCP port for one reached over TCP, the port and the speed for a serial one), each its own `radio/<id>/<field>`. */
export function boxKeys(radio: Pick<PageRadio, "id" | "type">): string[] {
  const type = typeOf(radio);
  const transport = type?.transport;
  const fields = (type?.fields ?? []).map((field) => field.key).filter((field) => !ELSEWHERE.includes(field));
  const either = fields.includes("port") && fields.some((field) => field.startsWith("tcp_")); // (a type with both a serial port and a TCP address among its fields: the ones of its way; else every field of its own, the host and port of a board on the network too)
  return fields
    .filter((field) => !either || (transport === "tcp" ? field !== "port" && field !== "baud" : !field.startsWith("tcp_")))
    .map((field) => `radio/${radio.id}/${field}`);
}

/** The fields of a radio that are not in its box in the Radio group: the beacon's and the status's Send on and the path (My station), the digipeater (the Digipeater group). */
const NOT_BOXED = ["beacon", "status", "path", "digipeat"];

/** Whether a key is of the Radio group's boxes: a radio's own field there (`radio/3/port`, its transmit level) or the main radio. */
export const boxedKey = (key: string): boolean => isRadioKey(key) && !NOT_BOXED.includes(fieldOfKey(key));

/** The id of the input of a key in the form: every "/" a "-" (`set-radio-3-port`, `set-station-call`). */
export const inputId = (key: string): string => `set-${fieldId(key)}`;

/** The word the ids of the radios' boxes start with where the page shows those boxes a second time: the setup guide's Radio step provides "setup" (`setup-radio-3-enabled`, `setup-radio-3-port`), so that no id is on
 * the page twice while the Settings tab's boxes are on it too (every tab stays mounted); none in the Settings tab (`set-radio-3-enabled`). */
export const BOX_IDS: InjectionKey<string> = Symbol("the ids of the radios' boxes");

/** An id of the radios' boxes in the place `word` names: the Settings tab's own where it names none, else the word in place of its `set-` (`set-radio-1-port` is `setup-radio-1-port`). */
export const placedId = (word: string, id: string): string => (word === "" ? id : `${word}-${id.replace(/^set-/, "")}`);

/** The ids of the boxes where the component that calls it (in its setup) is placed: BOX_IDS of the place, the Settings tab's own without one. */
export function boxIds(): (id: string) => string {
  const word = inject(BOX_IDS, "");
  return (id) => placedId(word, id);
}

/** The id of a radio's own element in the form (`set-radio-3-name`). */
export const radioElementId = (radio: Pick<PageRadio, "id">, part: string): string => `set-radio-${radio.id}-${part}`;

/** The id of a radio's Enable, the first control of its box (`set-radio-3-enabled`). */
export const enableId = (radio: Pick<PageRadio, "id">): string => radioElementId(radio, "enabled");

/** The change of a radio the page asked last (`radio_change`: which radio, which part), one for the page: the daemon's refusal of it names neither, and it belongs to the box that asked last, not to every box with a
 * change on its way. */
export interface Asked {
  radio: number;
  part: "enabled" | "type" | "name";
}
const asked = new WeakMap<object, ShallowRef<Asked | null>>();
/** The change asked last on this page (`page`: the page's context). */
export function askedOn(page: object): ShallowRef<Asked | null> {
  let found = asked.get(page);
  if (found === undefined) {
    found = shallowRef<Asked | null>(null);
    asked.set(page, found);
  }
  return found;
}

/** The proposal (a card or a keying) the page stored last from an answer to `list_ports`, one for every copy of the radio's box (the Settings tab's and the setup guide's are mounted together): refused, it is not
 * stored again from that answer by either. */
const proposed = new WeakMap<PortsMessage, { key: string; value: string }>();
/** Whether `value` for `key` is the proposal stored last from `answer`. */
export const proposedFrom = (answer: PortsMessage, key: string, value: string): boolean => {
  const last = proposed.get(answer);
  return last !== undefined && last.key === key && last.value === value;
};
/** The proposal is being stored from `answer`. */
export const proposing = (answer: PortsMessage, key: string, value: string): void => void proposed.set(answer, { key, value });

/** The name of a type of radio in the page's language: the catalogue id its row of RADIO_TYPES gives (`radio.type.lora_tcp`); the key itself only for a type this page does not know. */
export function typeText(key: string): string {
  const id = RADIO_TYPES.find((type) => type.key === key)?.text;
  return id !== undefined && hasMessage(id) ? t(id) : key;
}

/** The types of radio as a list to choose from: those of a kind (a radio's type changes within its kind), or all of them (Add radio), in the order of the daemon's list; without the types whose program this
 * installation does not carry (`unavailable`, the status's `unavailable_types`). */
export const typeChoices = (kind?: PageRadio["kind"], unavailable: readonly string[] = []): Choice[] =>
  RADIO_TYPES.filter((type) => (kind === undefined || type.kind === kind) && !unavailable.includes(type.key)).map((type) => ({
    value: type.key,
    label: typeText(type.key),
  }));

/** The groups of Add radio's list, in their order: each kind's real types (by the kind's word), then the Dummy types of every kind, for trying the program out. */
const ADD_GROUPS: readonly { word: MessageId; holds: (type: RadioType) => boolean }[] = [
  ...Object.entries(KIND_NAMES).map(([kind, word]) => ({ word, holds: (type: RadioType) => !type.dummy && type.kind === kind })),
  { word: "radio.add.without_radio", holds: (type: RadioType) => type.dummy },
];

/** Add radio's list of every type, in groups under their headings (ADD_GROUPS): within a group in the order of the daemon's list, the types that only receive last; without the types this installation does not carry
 * (`unavailable`). A group with no type in it has no heading either, as its options are none. */
export const addTypeChoices = (unavailable: readonly string[] = []): Choice[] =>
  ADD_GROUPS.flatMap(({ word, holds }) => {
    const types = RADIO_TYPES.filter((type) => holds(type) && !unavailable.includes(type.key));
    return [...types.filter((type) => type.can.transmit), ...types.filter((type) => !type.can.transmit)].map((type) => ({
      value: type.key,
      label: typeText(type.key),
      group: t(word),
    }));
  });

/** The words of a box's legend by the kind of its radio. */
const BOX_WORDS: Record<PageRadio["kind"], MessageId> = { fm: "settings.group.fm_radio", hf: "settings.group.hf_radio", lora: "settings.group.lora_radio" };

/** The legend of a radio's box: while the radio is named (`named`: the station has several radios) the name the operator typed, else the box's word of its kind with its number in the kind from the second on ("FM radio",
 * "HF radio 2"). */
export function boxTitle(radio: Pick<PageRadio, "row">, named: boolean): string {
  const { name, kind, number } = radio.row;
  if (named && name !== "") return name;
  const word = t(BOX_WORDS[kind]);
  return number > 1 ? `${word} ${number}` : word;
}

/** What a radio is called while it has no name of its own: its kind's word and its number ("HF 2"), the placeholder of its Name. */
export const unnamed = (radio: Pick<PageRadio, "row">): string => radioLabel({ ...radio.row, name: "" });

/** The radios that may repeat and are on, in the order of their boxes, each with the setting of its digipeater (`radio/<id>/digipeat`). */
function digipeaters(radios: readonly PageRadio[]): { radio: PageRadio; key: string }[] {
  return radios.filter((radio) => !radio.removed && radio.row.allowed.digipeat && radio.enabled).map((radio) => ({ radio, key: `radio/${radio.id}/digipeat` }));
}

/** The legend of a box in a group (components/SettingsBox.vue), with no (i): a radio's in the Digipeater group. */
interface Legend {
  text: string;
  title: string;
  tipLabel: string;
  tip: readonly string[];
}

/** What the Digipeater group shows: the setting of each radio's digipeater (`keys`), the row its counts are read from (`links`) and, while several radios are on (plan section 6: "each row with the radio's name when
 * there are several"), the legend of its box (`boxes`), so that each Enable says the radio it repeats on. */
export function digiPlaces(radios: readonly PageRadio[]) {
  const rows = digipeaters(radios);
  const several = enabledRadios(radios).length > 1;
  const links: Record<string, RadioRow | null> = Object.fromEntries(rows.map((row) => [row.key, row.radio.row]));
  const boxes: Record<string, Legend> = several
    ? Object.fromEntries(rows.map((row) => [row.key, { text: boxTitle(row.radio, true), title: "", tipLabel: "", tip: [] }]))
    : {};
  return { keys: rows.map((row) => row.key), links, boxes };
}
