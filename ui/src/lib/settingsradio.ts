// Which settings apply to the radios in use, and the keys of a radio's box in the Radio group
// (`radio/<id>/<key>` of `config.radio_values`, with the fields of its type from RADIO_TYPES).
import { inject, shallowRef, type InjectionKey, type ShallowRef } from "vue";
import { hasMessage, t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import type { PairLink } from "@/lib/digistatus";
import {
  enabledRadios,
  fieldId,
  KIND_WORDS as KIND_NAMES,
  radioLabel,
  senders,
  typeOf,
  type PageRadio,
  type RadioType,
} from "@/lib/radios";
import { pairCall } from "@/lib/settingspair";
import type { Choice } from "@/lib/settingchoices";
import type { PortsMessage, RadioRow } from "@/protocol/protocol";
import { RADIO_STATION_KEYS, RADIO_TYPES } from "@/protocol/lists";

/** Whether a station setting is a form field; the access key shows only while `network` is on. */
export function shownFor(key: string, network = true): boolean {
  if (key === "web/key" || key === "web/https") return network;
  return key !== "serial/last_port";
}

/** Settings for a moving station (SmartBeaconing). */
const MOVING_KEYS = ["beacon/travel"];

/** The key the Beacon group's Path fold is drawn by; the paths are per radio. */
const PATH_FOLD = "beacon/path";

/** Whether a setting applies to the radios that are on (beacon interval, SmartBeaconing, path). */
export function shownByRadios(key: string, radios: readonly PageRadio[]): boolean {
  const on = enabledRadios(radios);
  if (key === "beacon/interval_min") return on.length > 0;
  if (MOVING_KEYS.includes(key)) return on.some((radio) => radio.row.allowed.smart_beacon);
  if (key === PATH_FOLD) return on.some((radio) => radio.carriesPath);
  return true;
}

/** Whether a key belongs to a radio (`radio/3/port`, `pair/1/2/enabled`, `email/radio`). */
export const isRadioKey = (key: string): boolean =>
  key.startsWith("radio/") || key.startsWith("pair/") || (RADIO_STATION_KEYS as readonly string[]).includes(key);

/** Split `radio/3/port` into radio 3 and field `port`; null for any other key. */
export function radioFieldOf(key: string): { id: number; field: string } | null {
  const found = /^radio\/(\d+)\/([a-z_]+)$/.exec(key);
  return found === null ? null : { id: Number(found[1]), field: found[2] ?? "" };
}

/** The field part of a radio key (`port` for `radio/3/port`); the key itself otherwise. */
export const fieldOfKey = (key: string): string => radioFieldOf(key)?.field ?? key;

/** Maps a radio field to the lib/settings.ts FIELDS key that supplies its text and rules. */
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

/** Per-kind overrides of FIELD_WORDS: a LoRa board's address is a network address. */
const KIND_WORDS: Readonly<Partial<Record<PageRadio["kind"], Readonly<Record<string, string>>>>> = {
  lora: { tcp_host: "lora/host", tcp_port: "lora/port" },
};

/** The FIELDS key for a radio field, using the kind's override if any; null if none. */
export const flatKeyOf = (field: string, kind?: PageRadio["kind"]): string | null =>
  (kind === undefined ? undefined : KIND_WORDS[kind]?.[field]) ?? FIELD_WORDS[field] ?? null;

/** The per-radio "Send on" ticks: beacon, status, ask and local info. */
const SEND_ON = ["beacon", "status", "ask", "local_info"];

/** Radio fields not drawn as fields of the box: Send on ticks, path, digipeater, levels and PSK Reporter. */
const ELSEWHERE = [...SEND_ON, "path", "digipeat", "tx_gain_db", "tx_card", "rx_card", "psk_report", "psk_dial"];

/** The keys of the fields shown in a radio's status box. */
export function boxKeys(radio: Pick<PageRadio, "id" | "type">): string[] {
  const type = typeOf(radio);
  const transport = type?.transport;
  const fields = (type?.fields ?? []).map((field) => field.key).filter((field) => !ELSEWHERE.includes(field));
  // A type with both a serial port and a TCP address uses only the fields of its transport.
  const either = fields.includes("port") && fields.some((field) => field.startsWith("tcp_"));
  return fields
    .filter(
      (field) => !either || (transport === "tcp" ? field !== "port" && field !== "baud" : !field.startsWith("tcp_")),
    )
    .map((field) => `radio/${radio.id}/${field}`);
}

/** Radio fields that are not in the box: Send on ticks, path and digipeater. */
const NOT_BOXED = [...SEND_ON, "path", "digipeat"];

/** Whether a key is a field in a radio's box in the Radio group. */
export const boxedKey = (key: string): boolean => key.startsWith("radio/") && !NOT_BOXED.includes(fieldOfKey(key));

/** The input id of a key: every "/" becomes "-" (`set-radio-3-port`). */
export const inputId = (key: string): string => `set-${fieldId(key)}`;

/**
 * Prefix for the ids of the radios' boxes where the page shows them a second time. The setup
 * guide provides "setup", so no id appears twice (every tab stays mounted).
 */
export const BOX_IDS: InjectionKey<string> = Symbol("the ids of the radios' boxes");

/**
 * The id of a box element in the place `word` names (`set-radio-1-port` is `setup-radio-1-port`).
 */
export const placedId = (word: string, id: string): string => (word === "" ? id : `${word}-${id.replace(/^set-/, "")}`);

/** Returns the id mapper for the place the calling component is in (call from setup). */
export function boxIds(): (id: string) => string {
  const word = inject(BOX_IDS, "");
  return (id) => placedId(word, id);
}

/** The id of an element of a radio in the form (`set-radio-3-name`). */
export const radioElementId = (radio: Pick<PageRadio, "id">, part: string): string => `set-radio-${radio.id}-${part}`;

/** The id of a radio's Enable control (`set-radio-3-enabled`). */
export const enableId = (radio: Pick<PageRadio, "id">): string => radioElementId(radio, "enabled");

/**
 * The radio change the page asked last. The daemon's refusal names neither radio nor part, so
 * it is matched to the box that asked last.
 */
export interface Asked {
  radio: number;
  part: "enabled" | "type" | "name";
}
const asked = new WeakMap<object, ShallowRef<Asked | null>>();
/** The change asked last on this page (`page` is the page's context). */
export function askedOn(page: object): ShallowRef<Asked | null> {
  let found = asked.get(page);
  if (found === undefined) {
    found = shallowRef<Asked | null>(null);
    asked.set(page, found);
  }
  return found;
}

/**
 * The proposal (a sound card or keying) stored from an answer to `list_ports`. It is shared by all
 * copies of the radio's box, so a refused proposal is not stored again from the same answer.
 */
const proposed = new WeakMap<PortsMessage, { key: string; value: string }>();
/** Whether `value` for `key` is the proposal last stored from `answer`. */
export const proposedFrom = (answer: PortsMessage, key: string, value: string): boolean => {
  const last = proposed.get(answer);
  return last !== undefined && last.key === key && last.value === value;
};
/** Record the proposal stored from `answer`. */
export const proposing = (answer: PortsMessage, key: string, value: string): void =>
  void proposed.set(answer, { key, value });

/** The name of a radio type in the page's language; the key itself for an unknown type. */
export function typeText(key: string): string {
  const id = RADIO_TYPES.find((type) => type.key === key)?.text;
  return id !== undefined && hasMessage(id) ? t(id) : key;
}

/**
 * Radio types to choose from: those of one kind, or all (Add radio), in the daemon's order.
 * Types in `unavailable` are left out.
 */
export const typeChoices = (kind?: PageRadio["kind"], unavailable: readonly string[] = []): Choice[] =>
  RADIO_TYPES.filter((type) => (kind === undefined || type.kind === kind) && !unavailable.includes(type.key)).map(
    (type) => ({
      value: type.key,
      label: typeText(type.key),
    }),
  );

/** The groups of Add radio's list: each kind's real types, then the Dummy types of every kind. */
const ADD_GROUPS: readonly { word: MessageId; holds: (type: RadioType) => boolean }[] = [
  ...Object.entries(KIND_NAMES).map(([kind, word]) => ({
    word,
    holds: (type: RadioType) => !type.dummy && type.kind === kind,
  })),
  { word: "radio.add.without_radio", holds: (type: RadioType) => type.dummy },
];

/**
 * Add radio's list of every type, grouped under headings (ADD_GROUPS). Within a group, types that
 * can transmit come first. Types in `unavailable` and empty groups are left out.
 */
export const addTypeChoices = (unavailable: readonly string[] = []): Choice[] =>
  ADD_GROUPS.flatMap(({ word, holds }) => {
    const types = RADIO_TYPES.filter((type) => holds(type) && !unavailable.includes(type.key));
    return [...types.filter((type) => type.can.transmit), ...types.filter((type) => !type.can.transmit)].map(
      (type) => ({
        value: type.key,
        label: typeText(type.key),
        group: t(word),
      }),
    );
  });

/** The legend text of a box by radio kind. */
const BOX_WORDS: Record<PageRadio["kind"], MessageId> = {
  fm: "settings.group.fm_radio",
  hf: "settings.group.hf_radio",
  lora: "settings.group.lora_radio",
};

/**
 * The legend of a radio's box: the operator's name if `named` (several radios), else the kind's
 * word with its number from the second on ("FM radio", "HF radio 2").
 */
export function boxTitle(radio: Pick<PageRadio, "row">, named: boolean): string {
  const { name, kind, number } = radio.row;
  if (named && name !== "") return name;
  const word = t(BOX_WORDS[kind]);
  return number > 1 ? `${word} ${number}` : word;
}

/** The label of a radio without a name ("HF 2"); used as the Name placeholder. */
export const unnamed = (radio: Pick<PageRadio, "row">): string => radioLabel({ ...radio.row, name: "" });

/** The enabled radios that can digipeat, in box order, with their digipeat setting key. */
function digipeaters(radios: readonly PageRadio[]): { radio: PageRadio; key: string }[] {
  return radios
    .filter((radio) => !radio.removed && radio.row.allowed.digipeat && radio.enabled)
    .map((radio) => ({ radio, key: `radio/${radio.id}/digipeat` }));
}

/** The legend of a box in a group (components/SettingsBox.vue), with no (i). */
interface Legend {
  text: string;
  title: string;
  tipLabel: string;
  tip: readonly string[];
}

/** A legend of the Digipeater group's box. */
const legend = (text: string): Legend => ({ text, title: "", tipLabel: "", tip: [] });

/** What the status row under a Digipeater key shows: a radio's digipeater or a pair. */
type DigiStatus = { tnc: RadioRow } | { pair: PairLink };

/**
 * The pairs of radios offered, in box order: two enabled radios that can send, both Dummy or both
 * real, whose Enable the daemon reports in `values`.
 */
function pairs(radios: readonly PageRadio[], values: Readonly<Record<string, string>>) {
  const on = senders(radios).filter((radio) => !radio.removed);
  return on.flatMap((first, i) =>
    on.slice(i + 1).flatMap((second) => {
      const [low, high] = first.id < second.id ? [first.id, second.id] : [second.id, first.id];
      const enabled = `pair/${low}/${high}/enabled`;
      return first.dummy === second.dummy && enabled in values
        ? [{ first, second, enabled, ssid: `pair/${low}/${high}/ssid` }]
        : [];
    }),
  );
}

/** One radio of a pair as its status row reads it; the counts are read live. */
const pairEnd = (radio: PageRadio) => ({
  id: radio.id,
  name: boxTitle(radio, true),
  get stats() {
    return radio.row.stats;
  },
});

/**
 * What the Digipeater group shows (`values` is the form's): the keys (each radio's digipeater, then
 * each pair with its Call while on), the legends of the boxes (per radio when several are on,
 * always per pair) and the status row under a key.
 */
export function digiPlaces(radios: readonly PageRadio[], values: Readonly<Record<string, string>>) {
  const rows = digipeaters(radios);
  const several = enabledRadios(radios).length > 1;
  const offered = pairs(radios, values);
  const keys = [
    ...rows.map((row) => row.key),
    ...offered.flatMap((pair) => (values[pair.enabled] === "true" ? [pair.enabled, pair.ssid] : [pair.enabled])),
  ];
  const boxes: Record<string, Legend> = {
    ...(several ? Object.fromEntries(rows.map((row) => [row.key, legend(boxTitle(row.radio, true))])) : {}),
    ...Object.fromEntries(
      offered.map((pair) => [
        pair.enabled,
        legend(t("settings.pair.legend", { first: boxTitle(pair.first, true), second: boxTitle(pair.second, true) })),
      ]),
    ),
  };
  const status = Object.fromEntries([
    ...rows
      .filter((row) => values[row.key] === "true")
      .map((row): [string, DigiStatus] => [row.key, { tnc: row.radio.row }]),
    ...offered
      .filter((pair) => values[pair.enabled] === "true")
      .map((pair): [string, DigiStatus] => [
        pair.ssid,
        { pair: { first: pairEnd(pair.first), second: pairEnd(pair.second) } },
      ]),
  ]);
  const explain = Object.fromEntries(
    offered.map((pair) => [
      pair.enabled,
      {
        first: boxTitle(pair.first, true),
        second: boxTitle(pair.second, true),
        call: pairCall(pair.ssid, values),
        slow: [pair.first, pair.second].filter((r) => typeOf(r.row)?.limits.slow).map((r) => boxTitle(r, true)),
      },
    ]),
  );
  return { keys, boxes, status, explain };
}
