// What the radio group of the Settings tab says about the radio link in plain words: one status line instead of the daemon's counters, the ports a search listens to (`searching`, while the daemon looks for the radio), and the daemon's log lines
// (each with the time it was written, in UTC) in the viewer's time.
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import { ageText, bytesText, clockText, silentText } from "@/lib/format";
import type { ModemState, TncLine, TncState } from "@/protocol/protocol";

/** The ports the daemon listens to while it looks for the radio; null when it is not searching. */
export function searchedPorts(tnc: TncState): string[] | null {
  return tnc.path === "" && tnc.searching.length > 0 ? tnc.searching : null;
}

const STATES: Record<TncState["state"], MessageId> = {
  stopped: "settings.tnc.state.stopped",
  connecting: "settings.tnc.state.connecting",
  connected: "settings.tnc.state.connected",
  waiting: "settings.tnc.state.waiting",
  silent: "settings.tnc.state.silent",
};

/** The word on the pill for the state of the link. */
const stateText = (state: TncState["state"]): string => t(STATES[state]);

/** The HF radio: the rules of HF are the daemon's word for it (the Dummy HF radio too, which has no modem). */
const isHf = (tnc: TncState): boolean => tnc.rules.kind === "hf";

/** The pill of the radio: the state of the link, and for the Dummy radio, once its line is open, "Dummy" in the muted pill (it is nothing to be glad or sorry about). */
const dummyShown = (tnc: TncState): boolean => tnc.dummy && tnc.state === "connected";
export const pillText = (tnc: TncState): string => (dummyShown(tnc) ? t("settings.tnc.dummy_pill") : stateText(tnc.state));
export const pillClass = (tnc: TncState): string => (dummyShown(tnc) ? "tnc-dummy" : `tnc-${tnc.state}`);

/** "Last packet 2 min ago", "No packet yet". */
function lastPacketText(tnc: TncState, nowMs: number): string {
  const last = tnc.stats.last_packet;
  return last === null ? t("settings.tnc.no_packet") : t("settings.tnc.last_packet", { span: ageText(last, nowMs) });
}

/** What the Mercury HF modem does, in a word: the tune tone, the keying test, a frame on the air, a busy channel, else listening. */
function modemWord(modem: ModemState): string {
  if (modem.test === "tune") return t("settings.tnc.tuning");
  if (modem.test === "key") return t("settings.tnc.keyed");
  if (modem.keyed) return t("settings.tnc.transmitting");
  if (modem.busy) return t("settings.tnc.busy");
  return t("settings.tnc.listening");
}

/** The HF radio's line while the modem runs: what the operator can act on and nothing of the plumbing: "DATAC3 · Listening · SNR 3 dB · Last packet 2 min ago" (the SNR once a frame was decoded). The socket the daemon reaches the modem on is the log's. */
function modemLine(tnc: TncState, modem: ModemState, nowMs: number): string {
  const parts = [modem.mode, modemWord(modem)];
  if (modem.snr !== null) parts.push(t("settings.tnc.snr", { db: Math.round(modem.snr) }));
  parts.push(lastPacketText(tnc, nowMs));
  return parts.join(" · ");
}

/** The one line: "Last packet 2 min ago" when connected (the pill says connected and the Port field below names the port), "Searching for the radio…", "Not connected: no KISS frames on the port", "nothing heard since 02:43 (5 h)"; for the Dummy radio that its traffic is made up and nothing goes on the air;
 * for the Mercury HF modem its mode, what it does (listening, transmitting, the channel busy, tuning, keyed), the SNR and the last packet. The HF radio never shows the address its modem is reached on: while it connects the line says so and no more. */
export function tncStatus(tnc: TncState, nowMs: number): string {
  if (dummyShown(tnc)) return t(isHf(tnc) ? "settings.tnc.dummy_hf" : "settings.tnc.dummy");
  if (tnc.state === "silent") return silentText(tnc.silent_since, nowMs);
  if (searchedPorts(tnc) !== null) return t("settings.tnc.searching");
  if (tnc.state === "connected" && tnc.modem) return modemLine(tnc, tnc.modem, nowMs);
  if (tnc.state === "connected") return lastPacketText(tnc, nowMs);
  if (tnc.state === "connecting") return tnc.path === "" || isHf(tnc) ? t("settings.tnc.connecting") : t("settings.tnc.connecting_to", { path: tnc.path });
  const why = tnc.problem || tnc.last_error;
  return why === "" ? t("settings.tnc.not_connected") : t("settings.tnc.not_connected_why", { why });
}

/** What the line's hover title adds: how much has come in and gone out. */
export function tncCounts(tnc: TncState): string {
  const { packets, bytes_in, bytes_out, digipeated } = tnc.stats;
  return t("settings.tnc.counts", { n: packets, bytes_in: bytesText(bytes_in), bytes_out: bytesText(bytes_out), digipeated });
}

/** A log line of the daemon with the time it was written in the viewer's time. */
export function lineText(line: TncLine): string {
  return `${clockText(line.at)}  ${line.text}`;
}
