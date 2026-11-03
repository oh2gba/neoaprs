// How a station or a packet reached us, as the page names it. The daemon marks every packet with the channel it came by (`via`: `rf` heard on the radio, `rf-gated` heard on the radio from an iGate that took it from the internet, `is` received from the internet
// itself, `dummy` made up by the Dummy radio) and counts each station's packets by channel; the labels are RF (the FM radio), HF (the HF radio; a packet of the log says it by its `radio`), iGate, Internet and Dummy, and a station heard in more than one way has them joined ("RF · Internet"). The radio is named only where there are two: while the HF radio is on (`named`) the FM radio's tag is "FM" beside "HF", else it is "RF" as it always was. Only what was on the air near us (RF, iGate and the Dummy radio's) is Nearby's and the routes'; a station
// known from the internet alone is marked so on the map, in the table and on its card. Plain functions of rows.
import { t } from "@/i18n";
import { agoWords } from "@/lib/format";
import { stationRadio } from "@/lib/radiosides";
import type { PacketRow, StationRow } from "@/protocol/protocol";

/** The ways a station can have been heard, in the order they are told. */
export type Channel = "rf" | "hf" | "gated" | "is" | "dummy";

type Heard = Pick<StationRow, "heard_rf" | "heard_fm" | "heard_hf" | "heard_rf_gated" | "heard_is" | "heard_dummy" | "is_me" | "own">;
type Times = Pick<StationRow, "last_rf_at" | "last_fm_at" | "last_hf_at" | "last_rf_gated_at" | "last_is_at" | "last_dummy_at">;

/** The channels a station was heard by, in the order RF, HF, iGate, Internet, Dummy (RF is the FM radio: a station heard on HF alone has HF only); none for a station nothing was heard of (our own station, our objects: they are not heard). */
export function channelsOf(row: Heard): Channel[] {
  const found: Channel[] = [];
  if (row.is_me || row.own) return found;
  if (row.heard_rf > 0 && stationRadio(row) === "fm") found.push("rf");
  if (row.heard_hf > 0) found.push("hf");
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

/** The word of a channel: the FM radio is "FM" where the radios are named (the HF radio is on), "RF" otherwise. */
const name = (channel: Channel, named: boolean): string => t(channel === "rf" && named ? "channel.fm" : `channel.${channel}`);
/** What a channel means, for its hover title. */
const meaning = (channel: Channel, named: boolean): string => t(channel === "rf" && named ? "channel.title.fm" : `channel.title.${channel}`);

/** The channels joined with a middle dot: "RF", "HF", "iGate", "Internet", "RF · HF". */
function joined(parts: string[]): string {
  return parts.reduce((all, part) => t("channel.join", { first: all, second: part }));
}

/** The small label of a row: how it was heard, "RF · Internet"; empty when nothing was heard (our own station, our objects). */
export function channelLabel(row: Heard, named = false): string {
  const parts = channelsOf(row).map((channel) => name(channel, named));
  return parts.length === 0 ? "" : joined(parts);
}

/** The tone of a channel's tag: the internet teal, the Dummy radio's dashed, the HF radio's violet, and the FM radio's and the iGate's the neutral grey (the words stay: the colour is not the only difference). */
type ChannelTone = "neutral" | "info" | "hf" | "dummy";
const toneOf = (channel: Channel): ChannelTone => (channel === "is" ? "info" : channel === "dummy" ? "dummy" : channel === "hf" ? "hf" : "neutral");

/** One tag for each way a station was heard (RF, HF, iGate, Internet, Dummy), so that a station heard in two ways has two small tags and not one long one that a narrow table would cut: the word, what it means for the hover title, and the tone. */
export function channelTags(row: Heard, named = false): { channel: Channel; label: string; title: string; tone: "neutral" | "info" | "hf" | "dummy" }[] {
  return channelsOf(row).map((channel) => ({
    channel,
    label: name(channel, named),
    title: meaning(channel, named),
    tone: toneOf(channel),
  }));
}

/** The tone of the tag of a packet's channel. */
export const packetTone = (via: PacketRow["via"], radio: PacketRow["radio"] = ""): ChannelTone => toneOf(packetChannel(via, radio));

/** What the label means, for its hover title. */
export function channelTitle(row: Heard, named = false): string {
  const parts = channelsOf(row).map((channel) => meaning(channel, named));
  return parts.length === 0 ? "" : parts.reduce((all, part) => t("channel.title_join", { first: all, second: part }));
}

/** When the station was last heard, by channel: "RF 3 min ago · Internet 40 s ago"; empty when nothing was heard. A station heard on HF too has its RF time from the FM radio alone (`last_rf_at` is the newest of both radios). */
export function heardByChannel(row: Heard & Times, nowMs: number, named = false): string {
  const at: Record<Channel, string | null> = {
    rf: row.heard_hf > 0 ? row.last_fm_at : row.last_rf_at,
    hf: row.last_hf_at,
    gated: row.last_rf_gated_at,
    is: row.last_is_at,
    dummy: row.last_dummy_at,
  };
  const parts = channelsOf(row).map((channel) => t("channel.ago", { channel: name(channel, named), when: agoWords(at[channel], nowMs) }));
  return parts.length === 0 ? "" : joined(parts);
}

/** The channel of a packet of the log: a packet heard on the radio (`rf`) is HF when it came on the HF radio (`radio`), else RF. */
export function packetChannel(via: PacketRow["via"], radio: PacketRow["radio"] = ""): Channel {
  return via === "rf-gated" ? "gated" : via === "is" ? "is" : via === "dummy" ? "dummy" : radio === "hf" ? "hf" : "rf";
}

/** The label of a packet's channel: "RF", "HF", "iGate", "Internet", "Dummy". */
export const packetLabel = (via: PacketRow["via"], radio: PacketRow["radio"] = "", named = false): string => name(packetChannel(via, radio), named);

/** What a packet's channel means, for its hover title and its detail. */
export const packetTitle = (via: PacketRow["via"], radio: PacketRow["radio"] = "", named = false): string => meaning(packetChannel(via, radio), named);
