// What the Settings tab's radio group says about a radio's link, from its row of the topic
// `radios`: one status line instead of the daemon's counters, and the daemon's log lines in the
// viewer's time. Coded problems are worded by lib/radios.ts `problemText`; the daemon's English
// problem text is never shown.
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

/** The pill text for the link state. */
const stateText = (state: RadioRow["state"]): string => t(STATES[state]);

/** "Last packet 2 min ago", "No packet yet". */
function lastPacketText(tnc: Pick<RadioRow, "stats">, nowMs: number): string {
  const last = tnc.stats.last_packet;
  return last === null ? t("settings.tnc.no_packet") : t("settings.tnc.last_packet", { span: ageText(last, nowMs) });
}

/**
 * What the Mercury HF modem is doing: tune tone, keying test, transmitting, busy, else listening.
 */
function modemWord(modem: ModemState): string {
  if (modem.test === "tune") return t("settings.tnc.tuning");
  if (modem.test === "key") return t("settings.tnc.keyed");
  if (modem.keyed) return t("settings.tnc.transmitting");
  if (modem.busy) return t("settings.tnc.busy");
  return t("settings.tnc.listening");
}

/**
 * The two lines of a radio while its modem runs: what the modem does ("DATAC3 · Listening") and
 * when a packet last came with the last frame's SNR ("Last packet 2 min ago · SNR 3 dB").
 */
function modemParts(tnc: Pick<RadioRow, "stats">, modem: ModemState, nowMs: number): readonly [string, string] {
  const last = lastPacketText(tnc, nowMs);
  return [
    [modem.mode, modemWord(modem)].filter((part) => part !== "").join(" · "),
    modem.snr === null ? last : `${last} · ${t("settings.tnc.snr", { db: Math.round(modem.snr) })}`,
  ];
}

/**
 * Why the Mercury program is not running, as page words by the daemon's code (`ModemState.reason`).
 * A stopped program is quiet: the daemon restarts it and the operator can do nothing.
 */
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

/** The hover title's addition: how much has come in and gone out. */
function tncCounts(tnc: Pick<RadioRow, "stats">): string {
  const { packets, bytes_in, bytes_out, digipeated } = tnc.stats;
  return t("settings.tnc.counts", { n: packets, bytes_in: bytesText(bytes_in), bytes_out: bytesText(bytes_out), digipeated });
}

/** A daemon log line with its time in the viewer's time. */
export function lineText(line: TncLine): string {
  return `${clockText(line.at)}  ${line.text}`;
}

/** Whether a Dummy radio's line is open (shown at once, unlike a real radio's). */
const dummyRow = (row: RadioRow): boolean => row.dummy && row.state === "connected";

/** The pill text and class of a radio's row. */
export const rowPillText = (row: RadioRow): string => (dummyRow(row) ? t("settings.tnc.dummy_pill") : stateText(row.state));
export const rowPillClass = (row: RadioRow): string => (dummyRow(row) ? "tnc-dummy" : `tnc-${row.state}`);

/**
 * The parts of a connected radio's line, each on a fixed line so nothing below moves while the
 * radio receives and sends (components/StatusLine.vue `parts`): the modem's two, or the last
 * packet alone.
 * Null for every other line, which is one sentence that wraps and does not change per packet.
 */
export function rowParts(row: RadioRow, nowMs: number): readonly string[] | null {
  if (dummyRow(row) || row.state !== "connected" || row.problem?.code === "radio.text_lines") return null;
  return row.modem ? modemParts(row, row.modem, nowMs) : [lastPacketText(row, nowMs)];
}

/** The one status line of a radio's row. */
export function rowStatus(row: RadioRow, nowMs: number, radios?: RadioNames): string {
  if (dummyRow(row)) return t(row.kind === "hf" ? "settings.tnc.dummy_hf" : "settings.tnc.dummy");
  if (row.state === "silent") return silentText(row.problem?.code === "radio.silent" ? String(row.problem.params["since"] ?? "") || null : null, nowMs);
  // A LoRa board sending text lines: its link is open, but nothing goes until it is set to KISS.
  if (row.state === "connected" && row.problem?.code === "radio.text_lines") return problemText(row.problem, t, radios);
  const parts = rowParts(row, nowMs);
  if (parts !== null) return parts.join(" · ");
  return rowDownText(row, radios);
}

/**
 * A radio's line while not connected: searching, connecting, the modem's reason, or its problem.
 */
function rowDownText(row: RadioRow, radios?: RadioNames): string {
  if (row.problem?.code === "radio.searching") return t("settings.tnc.searching");
  if (row.state === "connecting") return t("settings.tnc.connecting");
  if (row.modem?.state === "waiting") return t(MODEM_WAITING[row.modem.reason]);
  // The program is starting or between two connection attempts: do not show the line's problem.
  if (row.modem && row.state === "waiting") return t("settings.tnc.connecting");
  return row.problem === null ? t("settings.tnc.not_connected") : problemText(row.problem, t, radios);
}

/** The counters of a radio's line, for its hover title. */
export const statsCounts = (stats: TncStats): string => tncCounts({ stats });
