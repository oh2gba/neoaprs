// What the boxes to write in say about the limits of a text and about Send, in one place: the title of the counter ("12 of 67 bytes left"), the counter itself ("12 left", "3 over") and why Send is off while the radio link is down.
/** The title of Send, and the reason of any button that sends, while the TNC is not connected. */
export const TNC_NOT_CONNECTED = "The TNC is not connected";

/** Why a button that sends is off: the TNC is not connected; undefined when it is. */
export function sendBlockedReason(connected: boolean): string | undefined {
  return connected ? undefined : TNC_NOT_CONNECTED;
}

/** What is left of a limit, for the counter of a box: "12 left", or "3 over" when the text is too long. */
export function leftText(left: number): string {
  return left < 0 ? `${-left} over` : `${left} left`;
}

/** The title of the counter: "12 of 67 bytes left" (`max` is the limit; without it "12 characters left"), and `rest` after it ("; the address and the space count too"). */
export function leftTitle(left: number, unit: "bytes" | "characters", max?: number, rest = ""): string {
  return `${left}${max === undefined ? "" : ` of ${max}`} ${unit} left${rest}`;
}
