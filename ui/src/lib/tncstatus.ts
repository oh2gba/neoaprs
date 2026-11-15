// What the radio group of the Settings tab says about a radio's link in plain words, from its row of the topic `radios`: one status line instead of the daemon's counters, and the daemon's log lines (each with the
// time it was written, in UTC) in the viewer's time. What a row does not carry (the port a search listens on, the daemon's English problem) is not said: its coded problem is (lib/radios.ts `problemText`).
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import type { RadioNames } from "@/i18n/errortext";
import { ageText, bytesText, clockText, silentText } from "@/lib/format";
import { problemText } from "@/lib/radios";
import type { ModemState, RadioRow, TncLine, TncStats } from "@/protocol/protocol";

const STATES: Record<RadioRow["state"], MessageId> = {
  stopped: "settings.tnc.state.stopped",
  connecting: "settings.tnc.state.connecting",
  connected: "settings.tnc.state.connected",
  waiting: "settings.tnc.state.waiting",
  silent: "settings.tnc.state.silent",
};

/** The word on the pill for the state of the link. */
const stateText = (state: RadioRow["state"]): string => t(STATES[state]);

/** "Last packet 2 min ago", "No packet yet". */
function lastPacketText(tnc: Pick<RadioRow, "stats">, nowMs: number): string {
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
function modemLine(tnc: Pick<RadioRow, "stats">, modem: ModemState, nowMs: number): string {
  const parts = [modem.mode, modemWord(modem)];
  if (modem.snr !== null) parts.push(t("settings.tnc.snr", { db: Math.round(modem.snr) }));
  parts.push(lastPacketText(tnc, nowMs));
  return parts.join(" · ");
}

/** Why the Mercury program is not running, in the page's words by the daemon's code (`ModemState.reason`; the English of `problem` is the log's and is never shown). A stopped program is quiet: the daemon starts it again and the operator can do nothing here. */
const MODEM_WAITING: Record<ModemState["reason"], MessageId> = {
  "": "settings.tnc.not_connected",
  not_installed: "settings.tnc.hf.not_installed",
  stopped: "settings.tnc.hf.stopped",
  network: "settings.tnc.hf.network",
  no_port: "settings.tnc.hf.no_port",
  not_started: "settings.tnc.hf.not_started",
  sound_card: "settings.tnc.hf.sound_card",
  keying: "settings.tnc.hf.keying",
};

/** What the line's hover title adds: how much has come in and gone out. */
function tncCounts(tnc: Pick<RadioRow, "stats">): string {
  const { packets, bytes_in, bytes_out, digipeated } = tnc.stats;
  return t("settings.tnc.counts", { n: packets, bytes_in: bytesText(bytes_in), bytes_out: bytesText(bytes_out), digipeated });
}

/** A log line of the daemon with the time it was written in the viewer's time. */
export function lineText(line: TncLine): string {
  return `${clockText(line.at)}  ${line.text}`;
}

/** A radio's line as its row says it, shown so only once it is open (a Dummy radio's line is open at once). */
const dummyRow = (row: RadioRow): boolean => row.dummy && row.state === "connected";

/** The word on the pill of a radio's row, and its colour. */
export const rowPillText = (row: RadioRow): string => (dummyRow(row) ? t("settings.tnc.dummy_pill") : stateText(row.state));
export const rowPillClass = (row: RadioRow): string => (dummyRow(row) ? "tnc-dummy" : `tnc-${row.state}`);

/** The one line of a radio's row: the Dummy's, silent since when, searching, the modem's line, the last packet, Connecting…, else why it is not connected. */
export function rowStatus(row: RadioRow, nowMs: number, radios?: RadioNames): string {
  if (dummyRow(row)) return t(row.kind === "hf" ? "settings.tnc.dummy_hf" : "settings.tnc.dummy");
  if (row.state === "silent") return silentText(row.problem?.code === "radio.silent" ? String(row.problem.params["since"] ?? "") || null : null, nowMs);
  if (row.state === "connected" && row.problem?.code === "radio.text_lines") return problemText(row.problem, t, radios); // (a LoRa board that sends text lines: its line is open, and nothing goes until it is set to KISS)
  if (row.state === "connected") return row.modem ? modemLine(row, row.modem, nowMs) : lastPacketText(row, nowMs);
  return rowDownText(row, radios);
}

/** A radio's line while it is not connected: searching, Connecting…, the modem's reason (Connecting… while the modem runs), else what its problem says. */
function rowDownText(row: RadioRow, radios?: RadioNames): string {
  if (row.problem?.code === "radio.searching") return t("settings.tnc.searching");
  if (row.state === "connecting") return t("settings.tnc.connecting");
  if (row.modem?.state === "waiting") return t(MODEM_WAITING[row.modem.reason]);
  if (row.modem && row.state === "waiting") return t("settings.tnc.connecting"); // (the program starts or runs and its line is between two attempts: nothing of the line's problem)
  return row.problem === null ? t("settings.tnc.not_connected") : problemText(row.problem, t, radios);
}

/** The counters of a radio's line, as the hover title of its status. */
export const statsCounts = (stats: TncStats): string => tncCounts({ stats });
