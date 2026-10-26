// What the boxes to write in say about the limits of a text and about Send, in one place: the title of the counter ("12 of 67 bytes left"), the counter itself ("12 left", "3 over") and why Send is off while the radio link is down.
import { t } from "@/i18n";

/** The title of Send, and the reason of any button that sends, while the TNC is not connected. */
export function tncNotConnected(): string {
  return t("compose.tnc_not_connected");
}

/** Why a button that sends is off: transmitting is switched off (RX only), or the TNC is not connected; undefined when neither. */
export function sendBlockedReason(connected: boolean, rxOnly = false): string | undefined {
  return rxOnly ? rxOnlyReason() : connected ? undefined : tncNotConnected();
}

/** The title of every button that sends while transmitting is switched off. */
export function rxOnlyReason(): string {
  return t("pill.rx_send");
}

/** What is left of a limit, for the counter of a box: "12 left", or "3 over" when the text is too long. */
export function leftText(left: number): string {
  return left < 0 ? t("compose.over", { n: -left }) : t("compose.left", { n: left });
}

/** What a counter counts, and so what its title says after the number: the bytes of a message, the characters of a bulletin, the characters of a mail (the address and the space count too), the characters of the comment of an object (no limit named). */
export type CountKind = "bytes" | "characters" | "address" | "comment";

/** The title of the counter: "12 of 67 bytes left" (`max` is the limit; the comment of an object has none named: "12 characters left in the comment"). */
export function leftTitle(left: number, kind: CountKind, max = 0): string {
  return t(`compose.left_title.${kind}`, { left, max });
}
