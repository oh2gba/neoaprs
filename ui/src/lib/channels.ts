// How a station or a packet reached us, as the page names it. The daemon marks every packet with the channel it came by (`via`: `rf` heard on the radio, `rf-gated` heard on the radio from an iGate that took it from the internet, `is` received from the internet
// itself, `dummy` made up by the Dummy radio) and counts each station's packets by channel; the labels are RF, iGate, Internet and Dummy, and a station heard in more than one way has them joined ("RF · Internet"). Only what was on the air near us (RF, iGate and the Dummy radio's) is Nearby's and the routes'; a station
// known from the internet alone is marked so on the map, in the table and on its card. Plain functions of rows.
import { t } from "@/i18n";
import { agoWords } from "@/lib/format";
import type { PacketRow, StationRow } from "@/protocol/protocol";

/** The ways a station can have been heard, in the order they are told. */
export type Channel = "rf" | "gated" | "is" | "dummy";

type Heard = Pick<StationRow, "heard_rf" | "heard_rf_gated" | "heard_is" | "heard_dummy" | "is_me" | "own">;
type Times = Pick<StationRow, "last_rf_at" | "last_rf_gated_at" | "last_is_at" | "last_dummy_at">;

/** The channels a station was heard by, in the order RF, iGate, Internet, Dummy; none for a station nothing was heard of (our own station, our objects: they are not heard). */
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

const name = (channel: Channel): string => t(`channel.${channel}`);

/** The channels joined with a middle dot: "RF", "iGate", "Internet", "RF · Internet". */
function joined(parts: string[]): string {
  return parts.reduce((all, part) => t("channel.join", { first: all, second: part }));
}

/** The small label of a row: how it was heard, "RF · Internet"; empty when nothing was heard (our own station, our objects). */
export function channelLabel(row: Heard): string {
  const parts = channelsOf(row).map(name);
  return parts.length === 0 ? "" : joined(parts);
}

/** The tone of the label's tag: the internet alone is info, what the Dummy radio made up is dummy, anything heard on the radio is neutral. */
export function channelTone(row: Heard): "neutral" | "info" | "dummy" {
  const channels = channelsOf(row);
  return channels.length === 1 && channels[0] === "is" ? "info" : channels.length === 1 && channels[0] === "dummy" ? "dummy" : "neutral";
}

/** The tone of the tag of a packet's channel. */
export const packetTone = (via: PacketRow["via"]): "neutral" | "info" | "dummy" => (via === "is" ? "info" : via === "dummy" ? "dummy" : "neutral");

/** What the label means, for its hover title. */
export function channelTitle(row: Heard): string {
  const parts = channelsOf(row).map((channel) => t(`channel.title.${channel}`));
  return parts.length === 0 ? "" : parts.reduce((all, part) => t("channel.title_join", { first: all, second: part }));
}

/** When the station was last heard, by channel: "RF 3 min ago · Internet 40 s ago"; empty when nothing was heard. */
export function heardByChannel(row: Heard & Times, nowMs: number): string {
  const at: Record<Channel, string | null> = { rf: row.last_rf_at, gated: row.last_rf_gated_at, is: row.last_is_at, dummy: row.last_dummy_at };
  const parts = channelsOf(row).map((channel) => t("channel.ago", { channel: name(channel), when: agoWords(at[channel], nowMs) }));
  return parts.length === 0 ? "" : joined(parts);
}

/** The channel of a packet of the log. */
export function packetChannel(via: PacketRow["via"]): Channel {
  return via === "rf-gated" ? "gated" : via === "is" ? "is" : via === "dummy" ? "dummy" : "rf";
}

/** The label of a packet's channel: "RF", "iGate", "Internet", "Dummy". */
export const packetLabel = (via: PacketRow["via"]): string => name(packetChannel(via));

/** What a packet's channel means, for its hover title and its detail. */
export const packetTitle = (via: PacketRow["via"]): string => t(`channel.title.${packetChannel(via)}`);
