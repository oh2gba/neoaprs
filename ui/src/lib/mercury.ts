// The two settings of the Mercury HF modem as the Radio group shows them: the sound card as a choice among what the daemon found (`sound_cards` of the ports message), and the keying
// as one choice built from the ports the daemon lists: the radio keys itself (VOX), a CM108 sound chip, or the RTS or DTR line of each serial port (`rts:/dev/ttyUSB0`), which is how the setting `mercury/keying` is written.
import { t } from "@/i18n";
import type { Choice } from "@/lib/settingchoices";
import { HF_PROFILES, LIMITS } from "@/protocol/lists";
import type { PortsMessage } from "@/protocol/protocol";

const LINES = ["rts", "dtr"] as const;

/** Whether the HF radio is the Mercury modem in these settings (`hf/profile`; Mercury unless they say the Dummy HF radio): the sound card, the keying, Tune and the keying test are the modem's. */
export const hfIsMercury = (values: Readonly<Record<string, string>>): boolean =>
  HF_PROFILES.find((p) => p.key === (values["hf/profile"] ?? ""))?.transport !== "dummy";

/** The sound cards as the choice of the Sound card field: the system's name for each, with the id as the hover title; a name that two cards share has its id after it. There is no choice of leaving it to the daemon: the daemon's proposal
 * (`soundCardPick`) is preselected and stored. */
export function soundCardChoices(ports: PortsMessage | null): Choice[] {
  const cards = ports?.sound_cards ?? [];
  return cards.map((c) => ({ value: c.id, label: cards.filter((o) => o.name === c.name).length > 1 ? `${c.name} (${c.id})` : c.name, title: c.id }));
}

/** The sound card the daemon proposes (the id), "" when none is listed. */
export const soundCardPick = (ports: PortsMessage | null): string => ports?.sound_cards.find((c) => c.pick)?.id ?? "";

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
