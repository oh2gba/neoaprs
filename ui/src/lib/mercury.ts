// The two settings of the Mercury HF modem as the Radio group shows them: the sound card as a list of what the daemon found (`sound_cards` of the ports message, shaped as a ports message so that the port's control shows it), and the keying
// as one choice built from the ports the daemon lists: the radio keys itself (VOX), a CM108 sound chip, or the RTS or DTR line of each serial port (`rts:/dev/ttyUSB0`), which is how the setting `mercury/keying` is written.
import { t } from "@/i18n";
import type { Choice } from "@/lib/settingchoices";
import { LIMITS } from "@/protocol/lists";
import type { PortsMessage } from "@/protocol/protocol";

const LINES = ["rts", "dtr"] as const;

/** The sound cards as a ports message: the id is the device, the system's name its description. */
export function soundCardPorts(ports: PortsMessage | null): PortsMessage | null {
  if (ports === null) return null;
  return {
    type: "ports",
    search: false,
    find: false,
    sound_cards: [],
    ports: ports.sound_cards.map((c) => ({ device: c.id, description: c.name, hwid: "n/a", vid: null, pid: null })),
  };
}

/** The words for a keying as the setting (or the daemon's choice) writes it: "RTS on /dev/ttyUSB0", "The radio keys itself (VOX)"; the text itself for one the page has no words for. */
export function keyingLabel(value: string): string {
  const [kind, device] = value.split(":", 2);
  if (kind === "vox") return t("settings.keying.vox");
  if (kind === "cm108") return t("settings.keying.cm108");
  if ((kind === "rts" || kind === "dtr") && device) return t(`settings.keying.${kind}`, { port: device });
  return value;
}

/** The ways of keying: the radio by itself, a CM108 chip, then RTS and DTR of every serial port the daemon lists (a Bluetooth device has no line to key with). The value in force stays offered when its port is not listed. */
export function keyingChoices(ports: PortsMessage | null, current = ""): Choice[] {
  const kinds = LIMITS.mercury.pttKinds;
  const plain: Choice[] = [
    { value: "vox", label: t("settings.keying.vox") },
    { value: "cm108", label: t("settings.keying.cm108") },
  ].filter((c) => (kinds as readonly string[]).includes(c.value));
  const devices = (ports?.ports ?? []).map((p) => p.device).filter((d) => !/^(bt|ble):\/\//i.test(d));
  const [kind, device] = current.split(":", 2);
  if (device && !devices.includes(device) && (LINES as readonly string[]).includes(kind ?? "")) devices.push(device);
  const lines = devices.flatMap((d) => LINES.map((line) => ({ value: `${line}:${d}`, label: t(`settings.keying.${line}`, { port: d }) })));
  return [...plain, ...lines];
}
