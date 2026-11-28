// The two settings of the Mercury HF modem as the Radio group shows them: the sound card as a
// choice among what the daemon found (`sound_cards` of the ports message), and the keying as
// one choice built from the ports the daemon lists: the radio keys itself (VOX), a CM108 sound
// chip, the RTS or DTR line of each serial port (`rts:/dev/ttyUSB0`), or a rig program the
// operator runs (`flrig`, `rigctld:10.0.0.2:4532`), which is how a radio's `keying` is written.
import { t } from "@/i18n";
import { heldChoice, type HolderOf } from "@/lib/portchoice";
import type { Choice } from "@/lib/settingchoices";
import { LIMITS } from "@/protocol/lists";
import type { PortsMessage } from "@/protocol/protocol";

const LINES = ["rts", "dtr"] as const;

/**
 * The sound cards as the choice of the Sound card field: the system's name for each; a name two
 * cards share gets its id after it; a card another radio
 * holds is greyed with its name (lib/portchoice.ts), unless it is the one in force, `current`.
 * There is no choice of leaving it to the daemon: the daemon's proposal (`soundCardPick`) is
 * preselected and stored.
 */
export function soundCardChoices(ports: PortsMessage | null, holder: HolderOf = () => null, current = ""): Choice[] {
  const cards = ports?.sound_cards ?? [];
  return cards.map((c) =>
    heldChoice(
      {
        value: c.id,
        label: cards.filter((o) => o.name === c.name).length > 1 ? `${c.name} (${c.id})` : c.name,
      },
      c.held_by,
      holder,
      current,
    ),
  );
}

/** The sound card the daemon proposes (the id), "" when none is listed. */
export const soundCardPick = (ports: PortsMessage | null): string => ports?.sound_cards.find((c) => c.pick)?.id ?? "";

/**
 * Separates the two devices of a Windows sound card in one id: the one it records from, then
 * the one it plays to (neoaprs/mercury.py, PAIR).
 */
const PAIR = "|";
/** How the id of a sound server's sink or source begins (neoaprs/soundserver.py). */
const SERVER = "pulse:DEVICE=";

/** The two halves of the sound: the device recorded from, the one played to. */
export type SoundHalf = "capture" | "playback";

/**
 * Whether the radio's sound is chosen as two devices: the daemon lists a sound server's sinks and
 * sources, any of which may be either half.
 */
export const soundCardSplit = (ports: PortsMessage | null): boolean =>
  (ports?.sound_cards ?? []).some((c) => c.id.startsWith(SERVER));

/** The device a setting records from and the one it plays to (neoaprs/mercurycards.py endpoints). */
export function soundCardHalves(value: string): [string, string] {
  const at = value.indexOf(PAIR);
  return at < 0 ? [value, value] : [value.slice(0, at), value.slice(at + 1)];
}

/** The setting of a device recorded from and one played to: one id where they are one card. */
export const soundCardJoin = (capture: string, playback: string): string =>
  capture === playback && !capture.startsWith(SERVER) ? capture : `${capture}${PAIR}${playback}`;

/** The words of a stored device the list no longer has; never its id. */
export const soundCardGone = (): string => t("settings.sound_card.gone");

/** The most of a device's description a field on a phone shows whole, and its two ends when longer. */
const SHORT = 26;
const HEAD = 12;
const TAIL = 13;

/**
 * A long description shortened in the middle at whole words: the device's name first and the way
 * last (Input, Output) are what tell the devices apart; a closing "(...)" goes first.
 */
function shortDevice(name: string): string {
  const plain = name.length > SHORT ? name.replace(/\s*\([^()]*\)$/, "") || name : name;
  if (plain.length <= SHORT) return plain;
  const words = plain.split(" ");
  let first = 1;
  while (first < words.length && words.slice(0, first + 1).join(" ").length <= HEAD) first++;
  let last = words.length - 1;
  while (last > first && words.slice(last - 1).join(" ").length <= TAIL) last--;
  const head = words.slice(0, first).join(" ").slice(0, HEAD);
  const tail = words.slice(Math.max(last, first)).join(" ").slice(-TAIL);
  return `${head}…${tail}`;
}

/**
 * The devices of one half as the choice of its field: what the operator named each, a source's
 * one channel with its number, and a name repeated with a count; a device another radio holds is
 * greyed (lib/portchoice.ts) unless it is the one in force.
 */
export function soundCardHalfChoices(
  ports: PortsMessage | null,
  half: SoundHalf,
  holder: HolderOf = () => null,
  current = "",
): Choice[] {
  const cards = (ports?.sound_cards ?? []).filter((c) => c[half]);
  const names = cards.map((c) =>
    c.channel
      ? t("settings.sound_card.channel", { name: shortDevice(c.name), channel: c.channel })
      : shortDevice(c.name),
  );
  return cards.map((c, i) => {
    const name = names[i] ?? c.name;
    const count = names.slice(0, i + 1).filter((n) => n === name).length;
    const label = count > 1 ? t("settings.sound_card.repeated", { name, count }) : name;
    return heldChoice({ value: c.id, label }, c.held_by, holder, current);
  });
}

/**
 * The listed card that an older setting names otherwise: one of the two devices of a Windows
 * card, or a Linux card by its number (a reboot renumbers cards, so what the number means now
 * is what the station runs with now); "" when `value` is a listed card's id already or none
 * matches.
 */
export const soundCardWith = (ports: PortsMessage | null, value: string): string => {
  const cards = ports?.sound_cards ?? [];
  if (value === "" || value.includes(PAIR) || cards.some((c) => c.id === value)) return "";
  return (
    cards.find(
      (c) => (c.id.includes(PAIR) && c.id.split(PAIR).includes(value)) || (c.numbered !== "" && c.numbered === value),
    )?.id ?? ""
  );
};

/**
 * The ways of keying: the radio by itself, a CM108 chip, then RTS and DTR of every serial port
 * the daemon lists (a Bluetooth device has no line to key with), those of ports sitting with
 * the radio's sound card first (`group`: the card's `usb_group`). The value in force stays
 * offered when its port is not listed.
 */
export function keyingChoices(ports: PortsMessage | null, current = "", group: string | null = null): Choice[] {
  const kinds = LIMITS.mercury.pttKinds;
  const plain: Choice[] = [
    { value: "vox", label: t("settings.keying.vox") },
    { value: "cm108", label: t("settings.keying.cm108") },
  ].filter((c) => (kinds as readonly string[]).includes(c.value));
  const listed = (ports?.ports ?? []).filter((p) => !/^(bt|ble):\/\//i.test(p.device));
  const own = (p: (typeof listed)[number]): boolean => group !== null && p.usb_group === group;
  const devices = [...listed.filter(own), ...listed.filter((p) => !own(p))].map((p) => p.device);
  const [kind, device] = current.split(":", 2);
  if (device && !devices.includes(device) && (LINES as readonly string[]).includes(kind ?? "")) devices.push(device);
  const lines = devices.flatMap((d) =>
    LINES.map((line) => ({ value: `${line}:${d}`, label: t(`settings.keying.${line}`, { port: d }) })),
  );
  const rigs = LIMITS.mercury.rigKinds.map((rig) => ({
    value: rigKind(current) === rig ? current : rig,
    label: t(`settings.keying.${rig}`),
  }));
  return [...plain, ...lines, ...rigs];
}

/** The rig program a keying names (`flrig`, `rigctld`), "" for any other keying. */
export function rigKind(keying: string): string {
  const kind = (keying.split(":", 1)[0] ?? "").trim().toLowerCase();
  return (LIMITS.mercury.rigKinds as readonly string[]).includes(kind) ? kind : "";
}

/** The address after a rig program's name, "" for the program's own on this computer. */
export const rigAddress = (keying: string): string => {
  const at = keying.indexOf(":");
  return rigKind(keying) === "" || at < 0 ? "" : keying.slice(at + 1).trim();
};

/** The keying of a rig program with the address typed; an empty one leaves the program's own. */
export const withAddress = (kind: string, address: string): string =>
  address.trim() === "" ? kind : `${kind}:${address.trim()}`;

/** Where the rig program listens unless an address is typed. */
export const rigDefault = (kind: string): string => (LIMITS.mercury.rigAddress as Record<string, string>)[kind] ?? "";
