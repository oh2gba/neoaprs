// What kind of ship a ship is, in words, from the type of ship and cargo it sends by AIS (1 to 99; the second figure of 20 to 99 is the cargo it carries, which the card leaves out): a passenger ship, a cargo
// ship, a tanker, or one of the ships of the 30s and the 50s that have a figure of their own (fishing, sailing, a tug, a pilot...). A type that names no kind (the reserved ones, the spare ones) has none.
import type { MessageId } from "@/i18n/catalogue";

/** The kinds that have one figure of their own. */
const ONE: Readonly<Record<number, MessageId>> = {
  30: "layers.kind.fishing",
  31: "layers.kind.towing",
  32: "layers.kind.towing",
  33: "layers.kind.dredging",
  34: "layers.kind.diving",
  35: "layers.kind.military",
  36: "layers.kind.sailing",
  37: "layers.kind.pleasure",
  50: "layers.kind.pilot",
  51: "layers.kind.rescue",
  52: "layers.kind.tug",
  53: "layers.kind.tender",
  54: "layers.kind.anti_pollution",
  55: "layers.kind.law",
  58: "layers.kind.medical",
  59: "layers.kind.noncombatant",
};

/** The kinds that are a whole ten, by its first figure. */
const TENS: Readonly<Record<number, MessageId>> = {
  2: "layers.kind.wing_in_ground",
  4: "layers.kind.high_speed",
  6: "layers.kind.passenger",
  7: "layers.kind.cargo",
  8: "layers.kind.tanker",
  9: "layers.kind.other",
};

/** The kind of ship of an AIS type, as the catalogue's id; null where the type is not known or names no kind. */
export function shipKind(type: number | null): MessageId | null {
  if (type === null || !Number.isInteger(type) || type < 1 || type > 99) return null;
  return ONE[type] ?? TENS[Math.floor(type / 10)] ?? null;
}
