// Which settings are there for the radios in use: the fields of the FM radio's TNC profile (its transport), and what a radio that is off leaves out (the HF radio has no paths, no digipeater and no moving station).
// And the keys of a radio's box in the Radio group: the radios of before (radio 1 the FM radio, radio 2 the HF radio) are worked by the flat keys of the settings of before (`tnc/profile`, `serial/port`, `hf/enabled`,
// `mercury/keying`) while the daemon still tells them, so that a station of today sees and saves what it did; every other radio by its own `radio/<id>/<key>` of `config.radio_values`, its type's fields (RADIO_TYPES).
import { inject, shallowRef, type InjectionKey, type ShallowRef } from "vue";
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import { hfIsMercury } from "@/lib/mercury";
import { FM_ID, HF_ID, fmOn, hfOn } from "@/lib/radiosides";
import { fieldId, radioLabel, typeOf, type PageRadio, type RadioType } from "@/lib/radios";
import type { Choice } from "@/lib/settingchoices";
import { profileOf } from "@/lib/tncprofile";
import { tncOfRow } from "@/lib/tncstatus";
import type { TncState } from "@/protocol/protocol";
import { RADIO_STATION_KEYS, RADIO_TYPES } from "@/protocol/lists";

const SERIAL_ONLY = ["serial/port", "serial/baud"];
/** RX only (`station/transmit`), the first row of the Radio group: the station's, not a radio's. */
const RX_ONLY = "station/transmit";

/** Whether a setting is shown for the FM radio's chosen TNC profile: the host and port for one that is reached over TCP, the port and speed for a serial one (the sound card and the keying are the HF radio's and always there); the access key while the daemon lets the network in (`network`) and has made one.
 * The port the search found last is no field: the port's own control says it. */
export function shownFor(key: string, profileKey: string | undefined, network = true): boolean {
  if (key === "web/key" || key === "web/https") return network;
  if (key === "serial/last_port") return false;
  const profile = profileOf(profileKey);
  if (!profile) return true;
  if (key.startsWith("tcp/")) return profile.transport === "tcp";
  if (SERIAL_ONLY.includes(key)) return profile.transport === "serial";
  return true;
}

/** The keys that are there only for the FM radio, whose network has digipeaters: the path and the digipeater. */
const PATH_KEYS = ["beacon/path", "digi/enabled"];
/** What a moving station travels as: SmartBeaconing's preset, which is FM's. (The GPS itself, the Position choice and where the receiver is, stay: a station on HF alone can move, with the timed beacon.) */
const MOVING_KEYS = ["beacon/travel"];

/** Whether a setting is there for the radios that are on (`fm/enabled` and `hf/enabled` of the values): the one Beacon choice while any radio is, and the path, the digipeater and Travelling while FM is. */
export function shownByRadios(key: string, values: Readonly<Record<string, string>>, radios: readonly PageRadio[] | null = null): boolean {
  if (key === "beacon/interval_min") return fmOn(values) || hfOn(values);
  if (radios !== null && key === "beacon/path") return radios.some((radio) => radio.carriesPath); // (the Path rows: one for each radio on that may carry a path, SettingsPath.vue)
  if (radios !== null && MOVING_KEYS.includes(key)) return radios.some((radio) => radio.row.allowed.smart_beacon); // (Travelling: while a radio on does SmartBeaconing)
  if (PATH_KEYS.includes(key) || MOVING_KEYS.includes(key)) return fmOn(values);
  return true;
}

/** A radio's own setting (`radio/3/port`) or a station setting of the radios (`station/main_radio`): the places of the radios show them (the boxes of the Radio group, the main radio, the Digipeater group), not the groups of the form. */
export const isRadioKey = (key: string): boolean => key.startsWith("radio/") || (RADIO_STATION_KEYS as readonly string[]).includes(key);

/** The radio and the field of a radio's own setting: `radio/3/port` is radio 3's `port`; null for any other key. */
export function radioFieldOf(key: string): { id: number; field: string } | null {
  const found = /^radio\/(\d+)\/([a-z_]+)$/.exec(key);
  return found === null ? null : { id: Number(found[1]), field: found[2] ?? "" };
}

/** The settings of before that a radio of before is worked by: its Enable, its type and each field of its type by the field's key. */
interface Flat {
  id: number;
  enable: string;
  type: string;
  fields: Readonly<Record<string, string>>;
}
const FLAT: Record<"fm" | "hf", Flat> = {
  fm: {
    id: FM_ID,
    enable: "fm/enabled",
    type: "tnc/profile",
    fields: { port: "serial/port", baud: "serial/baud", tcp_host: "tcp/host", tcp_port: "tcp/port", digipeat: "digi/enabled", path: "beacon/path" },
  },
  hf: {
    id: HF_ID,
    enable: "hf/enabled",
    type: "hf/profile",
    fields: { sound_card: "mercury/sound_card", keying: "mercury/keying", tx_gain_db: "mercury/tx_gain_db" },
  },
};

/** The radio of before that a radio is, while the daemon tells the settings of before (`values` has its Enable): radio 1 of kind FM, radio 2 of kind HF, not removed; null for every other radio. */
export function flatOf(radio: Pick<PageRadio, "id" | "kind" | "removed">, values: Readonly<Record<string, string>>): Flat | null {
  if (radio.kind === "lora" || radio.removed) return null;
  const flat = FLAT[radio.kind];
  return flat.id === radio.id && flat.enable in values ? flat : null;
}

/** The key a field of a radio is saved by: the setting of before for a radio of before, else its own `radio/<id>/<field>`. */
function radioKey(radio: Pick<PageRadio, "id" | "kind" | "removed">, field: string, values: Readonly<Record<string, string>>): string {
  return flatOf(radio, values)?.fields[field] ?? `radio/${radio.id}/${field}`;
}

/** The field of a radio a key is: `radio/3/port` and `serial/port` are both `port`; the key itself for one that is neither. */
export function fieldOfKey(key: string): string {
  const own = radioFieldOf(key)?.field;
  if (own !== undefined) return own;
  for (const flat of Object.values(FLAT)) for (const [field, flatKey] of Object.entries(flat.fields)) if (flatKey === key) return field;
  return key;
}

/** The setting of before that stands for a radio's field (`port` is `serial/port`): what a radio's own setting is checked and described as, since the words and the rules of a port are the same for every radio; null for a field that has none. */
export function flatKeyOf(field: string): string | null {
  for (const flat of Object.values(FLAT)) {
    const key = flat.fields[field];
    if (key !== undefined) return key;
  }
  return null;
}

/** The fields of a radio that are shown elsewhere than behind its status: Send on and its path (My station), its digipeater (the Digipeater group) and the transmit level, which is a row of its own. */
const ELSEWHERE = ["beacon", "path", "digipeat", "tx_gain_db"];

/** The keys behind the status of a radio of before, as the Radio group has always shown them, out of the keys of the group (`keys`): for the HF radio its type first, then the sound card and the keying while it is the Mercury
 * modem; for the FM radio the rest (its type, the port and the speed or the host and the TCP port: the form leaves out what its type does not have). RX only, the two Enables and the transmit level are rows of their own. */
function flatBoxKeys(flat: Flat, keys: readonly string[], mercury: boolean): string[] {
  const own = [RX_ONLY, FLAT.fm.enable, FLAT.hf.enable, FLAT.hf.fields["tx_gain_db"]];
  const hfBox = flat.id === HF_ID;
  return keys.filter(
    (key) => !own.includes(key) && (key === FLAT.hf.type || key.startsWith("mercury/")) === hfBox && (hfBox && key.startsWith("mercury/") ? mercury : true),
  );
}

/** The keys behind the status of any other radio: its type's fields there (the host and the TCP port for one reached over TCP, the port and the speed for a serial one), each its own `radio/<id>/<field>`. */
function radioBoxKeys(radio: Pick<PageRadio, "id" | "type">): string[] {
  const type = typeOf(radio);
  const transport = profileOf(radio.type)?.transport;
  return (type?.fields ?? [])
    .map((field) => field.key)
    .filter((field) => !ELSEWHERE.includes(field))
    .filter((field) => (transport === "tcp" ? field !== "port" && field !== "baud" : !field.startsWith("tcp_")))
    .map((field) => `radio/${radio.id}/${field}`);
}

/** The keys a radio's box is worked by when the station has these settings, for the radio of before by the group's keys (`keys`). */
export function boxKeys(radio: PageRadio, keys: readonly string[], values: Readonly<Record<string, string>>): string[] {
  const flat = flatOf(radio, values);
  return flat === null ? radioBoxKeys(radio) : flatBoxKeys(flat, keys, hfIsMercury(values));
}

/** The id of the input of a key in the form: every "/" a "-" (`set-radio-3-port`, `set-serial-port`). */
export const inputId = (key: string): string => `set-${fieldId(key)}`;

/** The word the ids of the radios' boxes start with where the page shows those boxes a second time: the setup guide's Radio step provides "setup" (`setup-fm-enabled`, `setup-radio-3-port`, `setup-find-radio`), so that no id is on
 * the page twice while the Settings tab's boxes are on it too (every tab stays mounted); none in the Settings tab (`set-fm-enabled`). */
export const BOX_IDS: InjectionKey<string> = Symbol("the ids of the radios' boxes");

/** An id of the radios' boxes in the place `word` names: the Settings tab's own where it names none, else the word in place of its `set-` (`set-serial-port` is `setup-serial-port`, `find-radio` is `setup-find-radio`). */
export const placedId = (word: string, id: string): string => (word === "" ? id : `${word}-${id.replace(/^set-/, "")}`);

/** The ids of the boxes where the component that calls it (in its setup) is placed: BOX_IDS of the place, the Settings tab's own without one. */
export function boxIds(): (id: string) => string {
  const word = inject(BOX_IDS, "");
  return (id) => placedId(word, id);
}

/** The id of a radio's own element in the form (`set-radio-3-name`). */
export const radioElementId = (radio: Pick<PageRadio, "id">, part: string): string => `set-radio-${radio.id}-${part}`;

/** The id of a radio's Enable, the first control of its box: the setting of before's for a radio of before (`set-fm-enabled`), else its own (`set-radio-3-enabled`). */
export function enableId(radio: Pick<PageRadio, "id" | "kind" | "removed">, values: Readonly<Record<string, string>>): string {
  const flat = flatOf(radio, values);
  return flat === null ? radioElementId(radio, "enabled") : inputId(flat.enable);
}

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

/** The words of each type of radio, as the lists of types say it (the catalogue's ids cannot have the "-" of the keys). */
const TYPE_WORDS: Record<RadioType["key"], MessageId> = {
  "kenwood-tnc2": "radio.type.kenwood_tnc2",
  "kenwood-d710": "radio.type.kenwood_d710",
  kantronics: "radio.type.kantronics",
  kiss: "radio.type.kiss",
  "kiss-tcp": "radio.type.kiss_tcp",
  dummy: "radio.type.dummy",
  mercury: "radio.type.mercury",
  "dummy-hf": "radio.type.dummy_hf",
};

/** The name of a type of radio in the page's language; the key itself for one this page does not know. */
export function typeText(key: string): string {
  const id = Object.entries(TYPE_WORDS).find(([type]) => type === key)?.[1];
  return id === undefined ? key : t(id);
}

/** The types of radio as a list to choose from: those of a kind (a radio's type changes within its kind), or all of them (Add radio), in the order of the daemon's list. */
export const typeChoices = (kind?: PageRadio["kind"]): Choice[] =>
  RADIO_TYPES.filter((type) => kind === undefined || type.kind === kind).map((type) => ({ value: type.key, label: typeText(type.key) }));

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

/** Whether a radio is on as the form holds it: a radio of before by its Enable as it is being changed (`draft`), any other as the daemon told it. */
export function onInForm(radio: PageRadio, values: Readonly<Record<string, string>>, draft: Readonly<Record<string, string>>): boolean {
  const flat = flatOf(radio, values);
  if (flat === null) return radio.enabled;
  return flat.id === FM_ID ? fmOn(draft) : hfOn(draft);
}

/** The radios that may repeat and are on, in the order of their boxes, each with the setting of its digipeater (`digi/enabled` for the FM radio of before, else its own `radio/<id>/digipeat`). */
function digipeaters(
  radios: readonly PageRadio[],
  values: Readonly<Record<string, string>>,
  draft: Readonly<Record<string, string>>,
): { radio: PageRadio; key: string }[] {
  return radios
    .filter((radio) => !radio.removed && radio.row.allowed.digipeat && onInForm(radio, values, draft))
    .map((radio) => ({ radio, key: radioKey(radio, "digipeat", values) }));
}

/** The legend of a box in a group (components/SettingsBox.vue), with no (i): a radio's in the Digipeater group. */
interface Legend {
  text: string;
  title: string;
  tipLabel: string;
  tip: readonly string[];
}

/** What the Digipeater group shows: the setting of each radio's digipeater (`keys`), what its counts are read from (`links`: the FM radio of before's topic, `tnc`, else the radio's row in that shape) and, while several
 * radios are on (plan section 6: "each row with the radio's name when there are several"), the legend of its box (`boxes`), so that each Enable says the radio it repeats on. */
export function digiPlaces(
  radios: readonly PageRadio[],
  values: Readonly<Record<string, string>>,
  draft: Readonly<Record<string, string>>,
  tnc: TncState | null,
) {
  const rows = digipeaters(radios, values, draft);
  const several = radios.filter((radio) => !radio.removed && onInForm(radio, values, draft)).length > 1;
  const links: Record<string, TncState | null> = Object.fromEntries(
    rows.map((row) => [row.key, flatOf(row.radio, values) === null ? tncOfRow(row.radio.row) : tnc]),
  );
  const boxes: Record<string, Legend> = several
    ? Object.fromEntries(rows.map((row) => [row.key, { text: boxTitle(row.radio, true), title: "", tipLabel: "", tip: [] }]))
    : {};
  return { keys: rows.map((row) => row.key), links, boxes };
}
