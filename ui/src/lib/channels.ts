// How a station or a packet reached us, as the page names it. The daemon marks every packet with the channel it came by (`via`: `rf` heard on a radio, `rf-gated` heard on a radio from an iGate that took it from the
// internet, `is` received from the internet itself, `dummy` made up by a Dummy radio) and the radio it came on (`radio_id`), and counts each station's packets by channel and by radio (`heard`). What a radio heard is
// tagged with that radio, whatever the number of radios: its short name (the name typed, else its kind's word, "FM", "HF", "LoRa", "HF 2") in the tone of its kind, dimmed once it is removed; a Dummy radio's tag is
// dashed, and the one radio on, a Dummy, keeps the Dummy's mark. iGate and Internet are the network's, not radios, and are told after the radios. Only what was on the air near us (a radio, an iGate's,
// a Dummy's) is Nearby's and the routes'; a station known from the internet alone is marked so on the map, in the table and on its card. Plain functions of rows and of the radios (`radios`: every radio, removed ones
// too, in the order of their boxes: composables/useRadios.ts `all`).
import { t } from "@/i18n";
import { agoWords } from "@/lib/format";
import { enabledRadios, isNamed, type PageRadio, type RadioId } from "@/lib/radios";
import type { PacketRow, StationRow } from "@/protocol/protocol";

/** The tones of the tags of how a station or a packet was heard (components/TagMark.vue's): the internet sky, a Dummy dashed, the HF radio's inverse pill, LoRa's sage, a removed radio dimmed, the rest neutral. */
type HeardTone = "neutral" | "info" | "hf" | "lora" | "dummy" | "removed";

/** The ways a station can have been heard, in the order they are told: on the air (`rf`: which radio, `heard` says), iGate, Internet, Dummy. */
export type Channel = "rf" | "gated" | "is" | "dummy";
/** The channels a tag names by a word of its own: the network's two (iGate, Internet) and the Dummy's mark; what a radio heard is named by the radio. */
type Worded = Exclude<Channel, "rf">;

type Heard = Pick<StationRow, "heard_rf" | "heard_rf_gated" | "heard_is" | "heard_dummy" | "is_me" | "own"> & Partial<Pick<StationRow, "heard">>;
type Times = Pick<StationRow, "last_rf_at" | "last_rf_gated_at" | "last_is_at" | "last_dummy_at">;

/** The channels a station was heard by, in the order the air (a radio), iGate, Internet, Dummy; none for a station nothing was heard of (our own station, our objects: they are not heard). Which radio heard
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
const name = (channel: Worded): string => t(`channel.${channel}`);
/** What a channel means, for its hover title. */
const meaning = (channel: Worded): string => t(`channel.title.${channel}`);

/** Parts joined with a middle dot: "FM", "iGate", "Internet", "FM · HF", "FM · Internet". */
function joined(parts: readonly string[]): string {
  return parts.length === 0 ? "" : parts.reduce((all, part) => t("channel.join", { first: all, second: part }));
}

/** Titles joined with a semicolon: the title of a "+n" tag (Stations, My objects). */
export function titled(parts: readonly string[]): string {
  return parts.length === 0 ? "" : parts.reduce((all, part) => t("channel.title_join", { first: all, second: part }));
}

/** The tone of a channel's tag: the internet sky, the Dummy radio's dashed, and the iGate's the neutral grey (the words stay: the colour is not the only difference). */
const toneOf = (channel: Worded): HeardTone => (channel === "is" ? "info" : channel === "dummy" ? "dummy" : "neutral");

/** The tone of a radio's tag: by its kind (the HF radio's inverse pill, LoRa's sage, FM the neutral), dashed for a Dummy radio whatever its kind, dimmed once it is removed. */
export function radioTone(radio: Pick<PageRadio, "kind" | "dummy" | "removed">): HeardTone {
  if (radio.removed) return "removed";
  if (radio.dummy) return "dummy";
  return radio.kind === "hf" ? "hf" : radio.kind === "lora" ? "lora" : "neutral";
}

/** One way a station was heard, a radio or a channel, as a tag says it: its word, what it means, its tone and when it was last heard that way. */
export interface HeardPart {
  key: string;
  label: string;
  title: string;
  tone: HeardTone;
  at: string | null;
  /** its word is a word of the page (FM, HF, iGate; a radio with no typed name and no number): its time follows it plainly ("HF 3 min ago"); a typed name or a number takes a colon ("20 m: 3 min ago") */
  plain: boolean;
  /** a radio of the station's (not iGate, Internet) */
  radio: boolean;
  /** a Dummy radio's */
  dummy: boolean;
}

/** Whether what the radio `id` carried keeps the Dummy's mark (Dummy, dashed, what it means), as it always had: the radio is the one radio on, and a Dummy (or the packet was made up by one). */
const dummyMark = (radios: readonly PageRadio[], id: RadioId, madeUp = false): boolean =>
  !isNamed(radios, id) && (madeUp || radios.some((radio) => radio.id === id && radio.dummy));

/** The one radio that is on, a Dummy: its made-up packets keep the mark they always had, with when they were made last. */
function dummyPart(radio: PageRadio, at: string | null): HeardPart {
  return { ...channelPart("dummy", at), key: `radio-${radio.id}` };
}

/** The tag of the radio that heard it, whatever the number of radios: its short name ("FM", "HF", "LoRa", "20 m") in the tone of its kind, with the time that radio last heard the station; a Dummy radio that is the
 * one radio on keeps the Dummy's mark. Null for a radio the page does not know (in the instant before the topic tells it): no tag rather than a word that names no radio. */
function radioPart(id: RadioId, at: string | null, radios: readonly PageRadio[], row?: Heard & Times): HeardPart | null {
  const radio = radios.find((one) => one.id === id);
  if (radio === undefined) return null;
  if (dummyMark(radios, id)) return dummyPart(radio, row === undefined ? at : row.last_dummy_at);
  return {
    key: `radio-${id}`,
    label: radio.name,
    title: t("radio.heard_on", { name: radio.name }),
    tone: radioTone(radio),
    at,
    plain: radio.plain, // (its kind's word, "FM", "HF": no typed name, no number; never `row`, which a stats-only patch of the topic makes anew)
    radio: true,
    dummy: radio.dummy,
  };
}

/** A channel's tag: iGate, Internet, and the Dummy's mark where no Dummy radio says it. */
function channelPart(channel: Worded, at: string | null): HeardPart {
  return {
    key: channel,
    label: name(channel),
    title: meaning(channel),
    tone: toneOf(channel),
    at,
    plain: true,
    radio: channel === "dummy",
    dummy: channel === "dummy",
  };
}

/** Every way the station was heard: each radio that heard it on the air, in the order of the boxes, then iGate and Internet (and Dummy, where no Dummy radio says it). A station heard on the air only as an
 * iGate's third-party packets has no radio (the iGate says it), and a radio the page does not know has no tag; none for our own station and our objects. */
export function heardParts(row: Heard & Times, radios: readonly PageRadio[]): HeardPart[] {
  if (row.is_me || row.own) return [];
  const onAirCount = row.heard_rf + row.heard_dummy;
  const place = (id: RadioId): number => {
    const at = radios.findIndex((radio) => radio.id === id);
    return at < 0 ? radios.length + id : at; // (a radio the page does not know comes last: radioPart gives it no tag)
  };
  const ids = Object.entries(row.heard ?? {})
    .filter(([, heard]) => heard.count > 0)
    .map(([id, heard]) => ({ id: Number(id), at: heard.last_at }))
    .sort((a, b) => place(a.id) - place(b.id));
  const byRadio = onAirCount === 0 ? [] : ids.flatMap(({ id, at }) => radioPart(id, at, radios, row) ?? []);
  return [
    ...byRadio,
    ...(row.heard_rf_gated > 0 ? [channelPart("gated", row.last_rf_gated_at)] : []),
    ...(row.heard_is > 0 ? [channelPart("is", row.last_is_at)] : []),
    ...(row.heard_dummy > 0 && !byRadio.some((part) => part.dummy) ? [channelPart("dummy", row.last_dummy_at)] : []),
  ];
}

/** A part with its time: "FM 3 min ago", and beside a radio's typed name or number "20 m: 3 min ago" (a name is not a word of the sentence: the colon keeps it apart from the time). */
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

/** When the station was last heard, every way: "FM 3 min ago · Internet 40 s ago", "FM 3 min ago · HF 1 min ago", and beside a typed name or a number every part with a colon, "FM: 3 min ago · 20 m: 1 h ago ·
 * Internet: 40 s ago"; empty when nothing was heard. */
export function heardTimes(row: Heard & Times, radios: readonly PageRadio[], nowMs: number): string {
  const parts = heardParts(row, radios);
  const colon = parts.some((part) => !part.plain);
  return joined(parts.map((part) => timed(part, nowMs, colon)));
}

/** The words of how the station was heard, for a short row (the hover card's "Heard on"): null for a station heard on the one radio that is on alone (nothing to say: every station is); with several radios on, every
 * way with its time; a station known from the internet alone says what that means; else the words of its tags joined, "FM · Internet". */
export function heardWords(row: Heard & Times, radios: readonly PageRadio[], nowMs: number): string | null {
  const parts = heardParts(row, radios);
  const on = enabledRadios(radios);
  if (on.length > 1) return heardTimes(row, radios, nowMs);
  const [only] = parts;
  if (parts.length === 0 || (parts.length === 1 && only?.key === `radio-${on[0]?.id}` && !only.dummy)) return null;
  if (internetOnly(row)) return titled(parts.map((part) => part.title));
  return joined(parts.map((part) => part.label));
}

/** The channel of a packet of the log: the air (`rf`, which radio its tag says), iGate, Internet, Dummy. */
export function packetChannel(via: PacketRow["via"]): Channel {
  return via === "rf-gated" ? "gated" : via === "is" ? "is" : via === "dummy" ? "dummy" : "rf";
}

type Packet = Pick<PacketRow, "via"> & Partial<Pick<PacketRow, "radio_id" | "direction">>;

/** The tag of a channel's packet. */
const wordTag = (channel: Worded, title = meaning(channel)): HeardTag => ({ key: channel, label: name(channel), title, tone: toneOf(channel) });

/** The tag of a packet of the log (the Packets tab's Via, a station's traffic, the statistics' "By channel"): a packet of the air (ours too) is the radio's it came or went on, as heardParts tags that radio (its
 * name, a Dummy alone the Dummy's mark; the title of ours "Sent on radio FM"); an iGate's is iGate, saying in its title which radio heard it; Internet is Internet. Null for a packet of a radio the page does not know (in the instant before the topic
 * tells it): no tag. */
export function packetTag(packet: Packet, radios: readonly PageRadio[]): HeardTag | null {
  const id = packet.radio_id ?? null;
  const channel = packetChannel(packet.via);
  const radio = id === null ? undefined : radios.find((one) => one.id === id);
  if (channel === "is") return wordTag("is");
  if (channel === "gated")
    return wordTag("gated", radio === undefined ? meaning("gated") : titled([meaning("gated"), t("radio.heard_on", { name: radio.name })]));
  const part = id === null ? null : radioPart(id, null, radios);
  if (id === null || part === null) return channel === "dummy" ? wordTag("dummy") : null;
  if (dummyMark(radios, id, channel === "dummy")) return { ...wordTag("dummy"), key: part.key };
  const { key, label, title, tone } = part;
  return { key, label, title: packet.direction === "out" ? t("packets.sent_on", { name: label }) : title, tone }; // (ours went on the radio: it was not heard)
}

/** What "Came by" of a packet's detail says after its tag: a radio's "heard on radio FM", "heard on radio 20 m", else (iGate, Internet, the Dummy's mark) what the channel means; null where it has no tag. */
export function packetCameBy(packet: Packet, radios: readonly PageRadio[]): string | null {
  const tag = packetTag(packet, radios);
  if (tag === null) return null;
  const id = packet.radio_id ?? null;
  const radio = tag.key.startsWith("radio-") && id !== null ? radios.find((one) => one.id === id) : undefined;
  return radio !== undefined && !dummyMark(radios, radio.id, packet.via === "dummy") ? t("packets.came_by.radio", { name: tag.label }) : tag.title;
}
