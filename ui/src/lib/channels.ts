// How a station or a packet reached us, as the page names it. The daemon marks every packet with the channel it came by (`via`: `rf` heard on a radio, `rf-gated` heard on a radio from an iGate that took it from the
// internet, `is` received from the internet itself, `dummy` made up by a Dummy radio) and the radio it came on (`radio_id`), and counts each station's packets by channel and by radio (`heard`). A radio is named only
// where more than one is on, and always where it is off or removed (lib/radios.ts `isNamed`): a named radio's tag is its short name in the tone of its kind (dashed for a Dummy, dimmed once removed); the one radio that
// is on keeps the words it always had (RF, HF for an HF radio, Dummy for a Dummy one), in the tone of its kind (a LoRa radio's RF is sage, as its named tag is). iGate and Internet are channels, not radios, and are told after the radios. Only what was on the air near us (a radio, an iGate's,
// a Dummy's) is Nearby's and the routes'; a station known from the internet alone is marked so on the map, in the table and on its card. Plain functions of rows and of the radios (`radios`: every radio, removed ones
// too, in the order of their boxes: composables/useRadios.ts `all`).
import { t } from "@/i18n";
import { agoWords } from "@/lib/format";
import { enabledRadios, isNamed, type PageRadio, type RadioId } from "@/lib/radios";
import type { PacketRow, StationRow } from "@/protocol/protocol";

/** The tones of the tags of how a station or a packet was heard (components/TagMark.vue's): the internet sky, a Dummy dashed, the HF radio's inverse pill, LoRa's sage, a removed radio dimmed, the rest neutral. */
type HeardTone = "neutral" | "info" | "hf" | "lora" | "dummy" | "removed";

/** The ways a station can have been heard, in the order they are told. */
export type Channel = "rf" | "hf" | "gated" | "is" | "dummy";

type Heard = Pick<StationRow, "heard_rf" | "heard_rf_gated" | "heard_is" | "heard_dummy" | "is_me" | "own"> & Partial<Pick<StationRow, "heard">>;
type Times = Pick<StationRow, "last_rf_at" | "last_rf_gated_at" | "last_is_at" | "last_dummy_at">;

/** The channels a station was heard by, in the order RF (a radio of the air), iGate, Internet, Dummy; none for a station nothing was heard of (our own station, our objects: they are not heard). Which radio heard
 * it is `heard` (heardParts). */
export function channelsOf(row: Heard): Channel[] {
  const found: Channel[] = [];
  if (row.is_me || row.own) return found;
  if (row.heard_rf > 0) found.push("rf");
  if (row.heard_rf_gated > 0) found.push("gated");
  if (row.heard_is > 0) found.push("is");
  if (row.heard_dummy > 0) found.push("dummy");
  return found;
}

/** Whether the station is known from the internet alone: packets came over it and none was heard on the radio, not even from an iGate. */
export function internetOnly(row: Heard): boolean {
  return !row.is_me && !row.own && row.heard_is > 0 && row.heard_rf === 0 && row.heard_rf_gated === 0 && row.heard_dummy === 0;
}

/** Whether the station counts for what is on the air near us (Nearby, the filter "Heard on RF only"): anything but a station known from the internet alone. */
export const onAir = (row: Heard): boolean => !internetOnly(row);

/** Whether any station in the rows is known from the internet at all (the filter "Heard on RF only" is there only then). */
export function anyInternet(rows: Iterable<Heard>): boolean {
  for (const row of rows) if (channelsOf(row).includes("is")) return true;
  return false;
}

/** The word of a channel. */
const name = (channel: Channel): string => t(`channel.${channel}`);
/** What a channel means, for its hover title. */
const meaning = (channel: Channel): string => t(`channel.title.${channel}`);

/** Parts joined with a middle dot: "RF", "HF", "iGate", "Internet", "RF · HF". */
function joined(parts: readonly string[]): string {
  return parts.length === 0 ? "" : parts.reduce((all, part) => t("channel.join", { first: all, second: part }));
}

/** Titles joined with a semicolon: the title of a "+n" tag (Stations, My objects). */
export function titled(parts: readonly string[]): string {
  return parts.length === 0 ? "" : parts.reduce((all, part) => t("channel.title_join", { first: all, second: part }));
}

/** The tone of a channel's tag: the internet sky, the Dummy radio's dashed, the HF radio's inverse pill, and the FM radio's and the iGate's the neutral grey (the words stay: the colour is not the only difference). */
const toneOf = (channel: Channel): HeardTone => (channel === "is" ? "info" : channel === "dummy" ? "dummy" : channel === "hf" ? "hf" : "neutral");

/** The tone of a radio's tag: by its kind (the HF radio's inverse pill, LoRa's sage, FM the neutral), dashed for a Dummy radio whatever its kind, dimmed once it is removed. */
export function radioTone(radio: Pick<PageRadio, "kind" | "dummy" | "removed">): HeardTone {
  if (radio.removed) return "removed";
  if (radio.dummy) return "dummy";
  return radio.kind === "hf" ? "hf" : radio.kind === "lora" ? "lora" : "neutral";
}

/** One way a station was heard, a radio or a channel, as a tag says it: its word, what it means, its tone, when it was last heard that way, and whether it is a radio's name. */
export interface HeardPart {
  key: string;
  label: string;
  title: string;
  tone: HeardTone;
  at: string | null;
  /** a radio, named (several radios on, or this one off or removed) */
  named: boolean;
  /** its word is a word of the page (RF, HF, iGate; a radio with no typed name and no number): its time follows it plainly ("HF 3 min ago"); a typed name or a number takes a colon ("20 m: 3 min ago") */
  plain: boolean;
  /** a radio of the station's (not iGate, Internet) */
  radio: boolean;
  /** a Dummy radio's */
  dummy: boolean;
}

/** The word a radio's packets of the air always had where it is the one radio on: Dummy for a Dummy radio's, HF for an HF radio's, else RF (a LoRa radio's too: one radio is the page it always was). */
const wordOf = (radio: Pick<PageRadio, "dummy" | "kind">): Channel => (radio.dummy ? "dummy" : radio.kind === "hf" ? "hf" : "rf");

/** The tone of the one radio that is on, by its word: RF in the tone of the radio's kind (LoRa's sage, FM's neutral), the colour of its named tag; HF and Dummy their own. */
const unnamedTone = (radio: PageRadio, word: Channel): HeardTone => (word === "rf" ? radioTone(radio) : toneOf(word));

/** The one radio that is on, unnamed: the word it always had (RF, HF, Dummy) and when that radio last heard the station (a Dummy's: its made-up packets). */
function unnamedPart(radio: PageRadio, at: string | null, row?: Heard & Times): HeardPart {
  const channel = wordOf(radio);
  const when = row !== undefined && channel === "dummy" ? row.last_dummy_at : at;
  return {
    key: `radio-${radio.id}`,
    label: name(channel),
    title: meaning(channel),
    tone: unnamedTone(radio, channel),
    at: when,
    named: false,
    plain: true,
    radio: true,
    dummy: radio.dummy,
  };
}

/** A radio's tag: the one radio that is on has the word it always had; any other its short name, in the tone of its kind, with the time that radio last heard the station; a radio the page does not know (in the
 * instant before the topic tells it) the word of the air, unnamed. */
function radioPart(id: RadioId, at: string | null, radios: readonly PageRadio[], row?: Heard & Times): HeardPart {
  const radio = radios.find((one) => one.id === id);
  if (radio === undefined) return { ...channelPart("rf", at), key: `radio-${id}` };
  if (!isNamed(radios, id)) return unnamedPart(radio, at, row);
  return {
    key: `radio-${id}`,
    label: radio.name,
    title: t("radio.heard_on", { name: radio.name }),
    tone: radioTone(radio),
    at,
    named: true,
    plain: radio.plain, // (its kind's word, "FM", "HF": no typed name, no number; never `row`, which a stats-only patch of the topic makes anew)
    radio: true,
    dummy: radio.dummy,
  };
}

/** A channel's tag (iGate, Internet, Dummy, and the air where no radio says it). */
const channelPart = (channel: Channel, at: string | null): HeardPart => ({
  key: channel,
  label: name(channel),
  title: meaning(channel),
  tone: toneOf(channel),
  at,
  named: false,
  plain: true,
  radio: channel === "rf" || channel === "hf" || channel === "dummy",
  dummy: channel === "dummy",
});

/** The channels, each with its time: for a station heard on the air whose radios the row does not say. */
function channelParts(row: Heard & Times): HeardPart[] {
  const at: Record<Channel, string | null> = { rf: row.last_rf_at, hf: null, gated: row.last_rf_gated_at, is: row.last_is_at, dummy: row.last_dummy_at };
  return channelsOf(row).map((channel) => channelPart(channel, at[channel]));
}

/** Every way the station was heard: each radio that heard it on the air, in the order of the boxes, then iGate and Internet (and Dummy, where no Dummy radio says it). A station heard on the air only as an
 * iGate's third-party packets has no radio (the iGate says it); none for our own station and our objects. */
export function heardParts(row: Heard & Times, radios: readonly PageRadio[]): HeardPart[] {
  if (row.is_me || row.own) return [];
  const onAirCount = row.heard_rf + row.heard_dummy;
  const place = (id: RadioId): number => {
    const at = radios.findIndex((radio) => radio.id === id);
    return at < 0 ? radios.length + id : at; // (a radio the page does not know comes last)
  };
  const ids = Object.entries(row.heard ?? {})
    .filter(([, heard]) => heard.count > 0)
    .map(([id, heard]) => ({ id: Number(id), at: heard.last_at }))
    .sort((a, b) => place(a.id) - place(b.id));
  if (ids.length === 0 && onAirCount > 0) return channelParts(row);
  const byRadio = onAirCount === 0 ? [] : ids.map(({ id, at }) => radioPart(id, at, radios, row));
  return [
    ...byRadio,
    ...(row.heard_rf_gated > 0 ? [channelPart("gated", row.last_rf_gated_at)] : []),
    ...(row.heard_is > 0 ? [channelPart("is", row.last_is_at)] : []),
    ...(row.heard_dummy > 0 && !byRadio.some((part) => part.dummy) ? [channelPart("dummy", row.last_dummy_at)] : []),
  ];
}

/** A part with its time: "RF 3 min ago", and beside a radio's typed name or number "20 m: 3 min ago" (a name is not a word of the sentence: the colon keeps it apart from the time). */
function timed(part: HeardPart, nowMs: number, colon: boolean): string {
  const when = agoWords(part.at, nowMs);
  return colon ? t("radio.line", { name: part.label, line: when }) : t("channel.ago", { channel: part.label, when });
}

/** A tag of "Heard on". */
export interface HeardTag {
  key: string;
  label: string;
  title: string;
  tone: HeardTone;
}

/** How many radios "Heard on" shows by their tags (and My objects a row's radios); the rest are one tag "+n". */
export const HEARD_ON_RADIOS = 2;

/** The tags of "Heard on" (the Stations table): the radios that heard the station last, `room` of them, in the order of their boxes, then "+n" whose title lists the rest with their times, then iGate and Internet
 * (which are not counted among the radios). One tag for each, so that a station heard in two ways has two small tags and not one long one that a narrow table would cut. */
export function heardTags(row: Heard & Times, radios: readonly PageRadio[], nowMs: number, room = HEARD_ON_RADIOS): HeardTag[] {
  const parts = heardParts(row, radios);
  const ofRadios = parts.filter((part) => part.radio);
  const latest = [...ofRadios].sort((a, b) => (b.at ?? "").localeCompare(a.at ?? "")).slice(0, room);
  const shown = ofRadios.filter((part) => latest.includes(part));
  const rest = ofRadios.filter((part) => !latest.includes(part));
  const tag = ({ key, label, title, tone }: HeardPart): HeardTag => ({ key, label, title, tone });
  const colon = rest.some((part) => !part.plain); // (the rule of heardTimes: a colon on every part once one needs it)
  const more: HeardTag[] =
    rest.length === 0
      ? []
      : [{ key: "more", label: t("radio.more", { n: rest.length }), title: titled(rest.map((part) => timed(part, nowMs, colon))), tone: "neutral" }];
  return [...shown.map(tag), ...more, ...parts.filter((part) => !part.radio).map(tag)];
}

/** When the station was last heard, every way: "RF 3 min ago · Internet 40 s ago", "FM 3 min ago · HF 1 min ago", and beside a typed name or a number every part with a colon, "FM: 3 min ago · 20 m: 1 h ago ·
 * Internet: 40 s ago"; empty when nothing was heard. */
export function heardTimes(row: Heard & Times, radios: readonly PageRadio[], nowMs: number): string {
  const parts = heardParts(row, radios);
  const colon = parts.some((part) => !part.plain);
  return joined(parts.map((part) => timed(part, nowMs, colon)));
}

/** The words of how the station was heard, for a short row (the hover card's "Heard on"): null for a station heard on the one radio that is on alone (nothing to say); with several radios on, every way with its time; a
 * station known from the internet alone says what that means; else the words joined, "RF · Internet". */
export function heardWords(row: Heard & Times, radios: readonly PageRadio[], nowMs: number): string | null {
  const parts = heardParts(row, radios);
  if (parts.every((part) => part.radio && !part.named && part.label === name("rf"))) return null;
  if (enabledRadios(radios).length > 1) return heardTimes(row, radios, nowMs);
  if (internetOnly(row)) return titled(parts.map((part) => part.title));
  return joined(parts.map((part) => part.label));
}

/** The channel of a packet of the log: the air (`rf`, which radio its tag says), iGate, Internet, Dummy. */
export function packetChannel(via: PacketRow["via"]): Channel {
  return via === "rf-gated" ? "gated" : via === "is" ? "is" : via === "dummy" ? "dummy" : "rf";
}

/** The label of a packet's channel: "RF", "iGate", "Internet", "Dummy" (the Packets filter matches it; the radio's own word is its tag's). */
export const packetLabel = (via: PacketRow["via"]): string => name(packetChannel(via));

type Packet = Pick<PacketRow, "via"> & Partial<Pick<PacketRow, "radio_id">>;

/** The tag of a packet of the log (the Packets tab's Via, a station's traffic): a packet of the air is its radio's, by name where the radio is named, else the word it always had (RF, HF, Dummy); an iGate's says in
 * its title which radio heard it, where that is named; Internet is Internet. */
export function packetTag(packet: Packet, radios: readonly PageRadio[]): HeardTag {
  const id = packet.radio_id ?? null;
  const channel = packetChannel(packet.via);
  const radio = id === null ? undefined : radios.find((one) => one.id === id);
  if (channel === "is" || radio === undefined || id === null) return { key: channel, label: name(channel), title: meaning(channel), tone: toneOf(channel) };
  const named = isNamed(radios, id);
  if (channel === "gated") {
    const title = named ? titled([meaning("gated"), t("radio.heard_on", { name: radio.name })]) : meaning("gated");
    return { key: "gated", label: name("gated"), title, tone: toneOf("gated") };
  }
  if (!named) {
    const word = channel === "dummy" ? "dummy" : wordOf(radio); // (the one radio that is on: the word it always had)
    return { key: `radio-${id}`, label: name(word), title: meaning(word), tone: unnamedTone(radio, word) };
  }
  const { label, title, tone } = radioPart(id, null, radios);
  return { key: `radio-${id}`, label, title, tone };
}

/** What "Came by" of a packet's detail says after its tag: a radio named "heard on radio 20 m", the HF radio unnamed "heard on the HF radio", else what the channel means. */
export function packetCameBy(packet: Packet, radios: readonly PageRadio[]): string {
  const tag = packetTag(packet, radios);
  const id = packet.radio_id ?? null;
  if (tag.key.startsWith("radio-") && id !== null && isNamed(radios, id)) return t("packets.came_by.radio", { name: tag.label });
  if (tag.key.startsWith("radio-") && tag.tone === "hf") return t("packets.came_by.hf");
  return tag.title;
}
