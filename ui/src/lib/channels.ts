// How a station or a packet reached us. The daemon marks every packet with its channel (`via`: `rf`
// heard on a radio, `rf-gated` heard on a radio from an iGate, `is` received from the internet,
// `dummy` made up by a Dummy radio) and the radio it came on (`radio_id`), and counts each
// station's packets by channel and by radio (`heard`).
// A radio's tag shows its short name in the tone of its kind; iGate and Internet are not radios
// and follow the radios. Only what was on the air nearby counts for Nearby and the routes.
// `radios` holds every radio, removed ones too, in the order of useRadios `all`.
import { t } from "@/i18n";
import { agoWords } from "@/lib/format";
import { enabledRadios, isNamed, type PageRadio, type RadioId } from "@/lib/radios";
import type { PacketRow, StationRow } from "@/protocol/protocol";

/** Tones of the tags that say how a station or packet was heard (see components/TagMark.vue). */
type HeardTone = "neutral" | "info" | "hf" | "lora" | "dummy" | "removed";

/** The ways a station can have been heard, in display order. */
export type Channel = "rf" | "gated" | "is" | "dummy";
/** Channels a tag names by a word of its own; a radio is named by the radio. */
type Worded = Exclude<Channel, "rf">;

type Heard = Pick<StationRow, "heard_rf" | "heard_rf_gated" | "heard_is" | "heard_dummy" | "is_me" | "own"> &
  Partial<Pick<StationRow, "heard">>;
type Times = Pick<StationRow, "last_rf_at" | "last_rf_gated_at" | "last_is_at" | "last_dummy_at">;

/** The channels a station was heard by, in display order; none for our own station and objects. */
export function channelsOf(row: Heard): Channel[] {
  const found: Channel[] = [];
  if (row.is_me || row.own) return found;
  if (row.heard_rf > 0) found.push("rf");
  if (row.heard_rf_gated > 0) found.push("gated");
  if (row.heard_is > 0) found.push("is");
  if (row.heard_dummy > 0) found.push("dummy");
  return found;
}

/** Whether the station is known from the internet alone, with nothing heard on any radio. */
export function internetOnly(row: Heard): boolean {
  return (
    !row.is_me &&
    !row.own &&
    row.heard_is > 0 &&
    row.heard_rf === 0 &&
    row.heard_rf_gated === 0 &&
    row.heard_dummy === 0
  );
}

/** Whether the station counts for what is on the air nearby: anything but internet-only. */
export const onAir = (row: Heard): boolean => !internetOnly(row);

/** Whether any station in the rows is known from the internet. */
export function anyInternet(rows: Iterable<Heard>): boolean {
  for (const row of rows) if (channelsOf(row).includes("is")) return true;
  return false;
}

/** The word of a channel. */
const name = (channel: Worded): string => t(`channel.${channel}`);
/** What a channel means, for its hover title. */
const meaning = (channel: Worded): string => t(`channel.title.${channel}`);

/** Parts joined with a middle dot: "Packet · Mercury". */
function joined(parts: readonly string[]): string {
  return parts.length === 0 ? "" : parts.reduce((all, part) => t("channel.join", { first: all, second: part }));
}

/** Titles joined with a semicolon. */
export function titled(parts: readonly string[]): string {
  return parts.length === 0 ? "" : parts.reduce((all, part) => t("channel.title_join", { first: all, second: part }));
}

/** The tone of a channel's tag; the words stay, so colour is not the only difference. */
const toneOf = (channel: Worded): HeardTone => (channel === "is" ? "info" : channel === "dummy" ? "dummy" : "neutral");

/** The tone of a radio's tag: by kind, dashed for a Dummy radio, dimmed once removed. */
export function radioTone(radio: Pick<PageRadio, "kind" | "dummy" | "removed">): HeardTone {
  if (radio.removed) return "removed";
  if (radio.dummy) return "dummy";
  return radio.kind === "hf" ? "hf" : radio.kind === "lora" ? "lora" : "neutral";
}

/** One way a station was heard, as a tag says it. */
export interface HeardPart {
  key: string;
  label: string;
  title: string;
  tone: HeardTone;
  at: string | null;
  /** The word is a page word (no typed name, no number): the time follows plainly; otherwise a
   * colon. */
  plain: boolean;
  /** A radio of the station's, not iGate or Internet. */
  radio: boolean;
  /** A Dummy radio's. */
  dummy: boolean;
}

/** Whether what radio `id` carried keeps the Dummy's mark: it is the only radio on and a Dummy. */
const dummyMark = (radios: readonly PageRadio[], id: RadioId, madeUp = false): boolean =>
  !isNamed(radios, id) && (madeUp || radios.some((radio) => radio.id === id && radio.dummy));

/** The part for the only radio on, a Dummy: its made-up packets keep the Dummy's mark. */
function dummyPart(radio: PageRadio, at: string | null): HeardPart {
  return { ...channelPart("dummy", at), key: `radio-${radio.id}` };
}

/** The tag of the radio that heard it, with the time that radio last heard the station.
 * Null for a radio the page does not know yet. */
function radioPart(
  id: RadioId,
  at: string | null,
  radios: readonly PageRadio[],
  row?: Heard & Times,
): HeardPart | null {
  const radio = radios.find((one) => one.id === id);
  if (radio === undefined) return null;
  if (dummyMark(radios, id)) return dummyPart(radio, row === undefined ? at : row.last_dummy_at);
  return {
    key: `radio-${id}`,
    label: radio.name,
    title: t("radio.heard_on", { name: radio.name }),
    tone: radioTone(radio),
    at,
    // Never `row`: a stats-only patch of the topic makes it anew.
    plain: radio.plain,
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

/** Every way the station was heard: each radio in box order, then iGate, Internet and Dummy.
 * None for our own station and objects. */
export function heardParts(row: Heard & Times, radios: readonly PageRadio[]): HeardPart[] {
  if (row.is_me || row.own) return [];
  const onAirCount = row.heard_rf + row.heard_dummy;
  const place = (id: RadioId): number => {
    const at = radios.findIndex((radio) => radio.id === id);
    // A radio the page does not know comes last; radioPart gives it no tag.
    return at < 0 ? radios.length + id : at;
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

/** A part with its time: "Packet 3 min ago", or "20 m: 3 min ago" beside a typed name or number. */
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

/** How many radios "Heard on" shows by their tags; the rest are one tag "+n". */
export const HEARD_ON_RADIOS = 2;

/** The tags of "Heard on": the `room` radios that heard the station last, then "+n" whose title
 * lists the rest with their times, then iGate and Internet. */
export function heardTags(
  row: Heard & Times,
  radios: readonly PageRadio[],
  nowMs: number,
  room = HEARD_ON_RADIOS,
): HeardTag[] {
  const parts = heardParts(row, radios);
  const ofRadios = parts.filter((part) => part.radio);
  const latest = [...ofRadios].sort((a, b) => (b.at ?? "").localeCompare(a.at ?? "")).slice(0, room);
  const shown = ofRadios.filter((part) => latest.includes(part));
  const rest = ofRadios.filter((part) => !latest.includes(part));
  const tag = ({ key, label, title, tone }: HeardPart): HeardTag => ({ key, label, title, tone });
  // A colon on every part once one needs it, as in heardTimes.
  const colon = rest.some((part) => !part.plain);
  const more: HeardTag[] =
    rest.length === 0
      ? []
      : [
          {
            key: "more",
            label: t("radio.more", { n: rest.length }),
            title: titled(rest.map((part) => timed(part, nowMs, colon))),
            tone: "neutral",
          },
        ];
  return [...shown.map(tag), ...more, ...parts.filter((part) => !part.radio).map(tag)];
}

/** When the station was last heard, every way: "Packet 3 min ago · Internet 40 s ago". */
export function heardTimes(row: Heard & Times, radios: readonly PageRadio[], nowMs: number): string {
  const parts = heardParts(row, radios);
  const colon = parts.some((part) => !part.plain);
  return joined(parts.map((part) => timed(part, nowMs, colon)));
}

/** The words of how the station was heard, for the hover card: null when it was heard only on the
 * one radio that is on. */
export function heardWords(row: Heard & Times, radios: readonly PageRadio[], nowMs: number): string | null {
  const parts = heardParts(row, radios);
  const on = enabledRadios(radios);
  if (on.length > 1) return heardTimes(row, radios, nowMs);
  const [only] = parts;
  if (parts.length === 0 || (parts.length === 1 && only?.key === `radio-${on[0]?.id}` && !only.dummy)) return null;
  if (internetOnly(row)) return titled(parts.map((part) => part.title));
  return joined(parts.map((part) => part.label));
}

/** The channel of a logged packet. */
export function packetChannel(via: PacketRow["via"]): Channel {
  return via === "rf-gated" ? "gated" : via === "is" ? "is" : via === "dummy" ? "dummy" : "rf";
}

type Packet = Pick<PacketRow, "via"> & Partial<Pick<PacketRow, "radio_id" | "direction">>;

/** The tag of a channel's packet. */
const wordTag = (channel: Worded, title = meaning(channel)): HeardTag => ({
  key: channel,
  label: name(channel),
  title,
  tone: toneOf(channel),
});

/** The tag of what came over the Internet connection. */
export const internetTag = (): HeardTag => wordTag("is");

/** The tag of a logged packet: the radio it came or went on, iGate (its title names the radio
 * that heard it) or Internet. Null for a radio the page does not know yet. */
export function packetTag(packet: Packet, radios: readonly PageRadio[]): HeardTag | null {
  const id = packet.radio_id ?? null;
  const channel = packetChannel(packet.via);
  const radio = id === null ? undefined : radios.find((one) => one.id === id);
  if (channel === "is") return wordTag("is");
  if (channel === "gated")
    return wordTag(
      "gated",
      radio === undefined ? meaning("gated") : titled([meaning("gated"), t("radio.heard_on", { name: radio.name })]),
    );
  const part = id === null ? null : radioPart(id, null, radios);
  if (id === null || part === null) return channel === "dummy" ? wordTag("dummy") : null;
  if (dummyMark(radios, id, channel === "dummy")) return { ...wordTag("dummy"), key: part.key };
  const { key, label, title, tone } = part;
  // Our own packet went out on the radio; it was not heard.
  return { key, label, title: packet.direction === "out" ? t("packets.sent_on", { name: label }) : title, tone };
}

/** What "Came by" of a packet detail says after its tag; null where there is no tag. */
export function packetCameBy(packet: Packet, radios: readonly PageRadio[]): string | null {
  const tag = packetTag(packet, radios);
  if (tag === null) return null;
  const id = packet.radio_id ?? null;
  const radio = tag.key.startsWith("radio-") && id !== null ? radios.find((one) => one.id === id) : undefined;
  return radio !== undefined && !dummyMark(radios, radio.id, packet.via === "dummy")
    ? t("packets.came_by.radio", { name: tag.label })
    : tag.title;
}

/** The tag of the radio with id `id`, as a packet that radio heard has it; null for a radio the page
 * does not know yet. */
export function radioTag(id: RadioId, radios: readonly PageRadio[]): HeardTag | null {
  const part = radioPart(id, null, radios);
  if (part === null) return null;
  if (dummyMark(radios, id)) return { ...wordTag("dummy"), key: part.key };
  const { key, label, title, tone } = part;
  return { key, label, title, tone };
}
