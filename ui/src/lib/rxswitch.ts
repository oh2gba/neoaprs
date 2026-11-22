// The RX only switch at the right end of the header (components/RxSwitch.vue): the face it shows and
// what a press does, from `station/transmit` as it will be once the page's saves are answered,
// whether no radio that is on can send, and the page's socket.
import type { MessageId } from "@/i18n/catalogue";
import type { Connection } from "@/lib/hub";
import { DAEMON_STATES, radioFocus } from "@/lib/pills";
import type { PageRadio } from "@/lib/radios";

export const RX_SWITCH_ID = "rx-switch";

export interface RxSwitch {
  face: "rx" | "tx";
  /** `toggle` sends the setting, `open` leads to the radio's box (`focus`), `none` does nothing. */
  act: "toggle" | "open" | "none";
  title: MessageId;
  focus: string;
}

/**
 * The switch for `transmit` (the setting's text), `listening` (no radio that is on can send; `first`
 * is the first radio that is on) and the socket: no press while it is not open, the face kept.
 */
export function rxSwitch(
  transmit: string,
  listening: boolean,
  connection: Connection,
  first: PageRadio | undefined,
): RxSwitch {
  const shown: RxSwitch =
    transmit === "false"
      ? { face: "rx", act: "toggle", title: "header.rx.rx_title", focus: "" }
      : listening
        ? { face: "rx", act: "open", title: "pill.rx_title_radios", focus: radioFocus(first) }
        : { face: "tx", act: "toggle", title: "header.rx.tx_title", focus: "" };
  return connection === "open" ? shown : { ...shown, act: "none", title: DAEMON_STATES[connection].title };
}
