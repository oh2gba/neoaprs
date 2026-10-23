// What the radio group of the Settings tab says about the radio link in plain words: one status line instead of the daemon's counters, the ports a search listens to (`searching`, while the daemon looks for the radio), and the daemon's log lines
// (each with the time it was written, in UTC) in the viewer's time.
import { ageText, bytesText, clockText, silentText } from "@/lib/format";
import type { TncLine, TncState } from "@/protocol/protocol";

/** The ports the daemon listens to while it looks for the radio; null when it is not searching. */
export function searchedPorts(tnc: TncState): string[] | null {
  return tnc.path === "" && tnc.searching.length > 0 ? tnc.searching : null;
}

function lastPacketText(tnc: TncState, nowMs: number): string {
  return tnc.stats.last_packet === null ? "No packet yet" : `Last packet ${ageText(tnc.stats.last_packet, nowMs)} ago`;
}

/** The one line (with how many packets the digipeater repeated, while it is on): "Last packet 2 min ago" when connected (the pill says connected and the Port field below names the port), "Searching for the radio…", "Not connected: no KISS frames on the port", "nothing heard since 02:43 (5 h)". */
export function tncStatus(tnc: TncState, nowMs: number, digipeater = false): string {
  if (tnc.state === "silent") return silentText(tnc.silent_since, nowMs);
  if (searchedPorts(tnc) !== null) return "Searching for the radio…";
  if (tnc.state === "connected") {
    const digipeated = digipeater && tnc.stats.digipeated > 0 ? `, digipeated ${tnc.stats.digipeated}` : "";
    return `${lastPacketText(tnc, nowMs)}${digipeated}`;
  }
  if (tnc.state === "connecting") return tnc.path === "" ? "Connecting…" : `Connecting to ${tnc.path}…`;
  const why = tnc.problem || tnc.last_error;
  return why === "" ? "Not connected" : `Not connected: ${why}`;
}

/** What the line's hover title adds: how much has come in and gone out. */
export function tncCounts(tnc: TncState): string {
  const { packets, bytes_in, bytes_out, digipeated } = tnc.stats;
  return `${packets} ${packets === 1 ? "packet" : "packets"} heard, ${bytesText(bytes_in)} in, ${bytesText(bytes_out)} out, ${digipeated} digipeated`;
}

/** A log line of the daemon with the time it was written in the viewer's time. */
export function lineText(line: TncLine): string {
  return `${clockText(line.at)}  ${line.text}`;
}
