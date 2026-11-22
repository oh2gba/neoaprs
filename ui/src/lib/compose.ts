// What the boxes to write in say about the limits of a text and about Send: the title of the
// counter ("12 of 67 bytes left"), the counter itself ("12 left", "3 over") and why Send is off
// while the radio link is down.
import { t } from "@/i18n";
import type { PageRadio } from "@/lib/radios";

/**
 * The title of Send, and the reason of any button that sends, while the TNC is not connected.
 */
export function tncNotConnected(): string {
  return t("compose.tnc_not_connected");
}

/**
 * Why a button that sends is off: transmitting is switched off (RX only), or the TNC is not
 * connected; undefined when neither.
 */
export function sendBlockedReason(connected: boolean, rxOnly = false): string | undefined {
  return rxOnly ? rxOnlyReason() : connected ? undefined : tncNotConnected();
}

/**
 * Why nothing may go on a radio: it is not connected (named when several are on or it is off),
 * or there is none; undefined while it is connected, and while `told` is false (before the
 * daemon has told its radios).
 */
export function radioBlockedReason(
  radio: PageRadio | null | undefined,
  named: boolean,
  told = true,
): string | undefined {
  if (!told || radio?.connected === true) return undefined;
  return radio == null
    ? t("error.radio.none")
    : named
      ? t("radio.not_connected", { name: radio.name })
      : tncNotConnected();
}

/** The title of every button that sends while transmitting is switched off. */
export function rxOnlyReason(): string {
  return t("error.transmit.off");
}

/**
 * What is left of a limit, for a box's counter: "12 left", or "3 over" when the text is too
 * long.
 */
export function leftText(left: number): string {
  return left < 0 ? t("compose.over", { n: -left }) : t("compose.left", { n: left });
}

/**
 * What a counter counts, and so what its title says after the number: bytes of a message,
 * characters of a bulletin, characters of a mail (the address and the space count too),
 * characters of an object's comment (no limit named).
 */
export type CountKind = "bytes" | "characters" | "address" | "comment";

/**
 * The title of the counter: "12 of 67 bytes left" (`max` is the limit; an object's comment has
 * none named: "12 characters left in the comment").
 */
export function leftTitle(left: number, kind: CountKind, max = 0): string {
  return t(`compose.left_title.${kind}`, { left, max });
}
