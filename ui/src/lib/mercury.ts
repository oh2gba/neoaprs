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
 * The sound cards as the choice of the Sound card field: the system's name for each, with the
 * id as the hover title; a name two cards share gets its id after it; a card another radio
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
        title: c.id,
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
