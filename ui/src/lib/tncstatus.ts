// What the radio group of the Settings tab says about the radio link in plain words: one status line instead of the daemon's counters, the ports a search listens to (told in the daemon's `describe` line while it looks for the radio), and the daemon's log lines
// (which begin with the time in UTC) in the viewer's time.
import { ageText, bytesText, clockText, silentText } from "@/lib/format";
import type { TncState } from "@/protocol/protocol";

const SEARCHING = /^listening on (.+) for the radio$/;
const LINE_TIME = /^(\d\d):(\d\d):(\d\d)(?=\s|$)/;
const DAY_MS = 24 * 60 * 60 * 1000;

/** The ports the daemon listens to while it looks for the radio (`describe`: "listening on /dev/ttyUSB0, /dev/ttyUSB1 for the radio"); null when it is not searching. */
export function searchedPorts(tnc: TncState): string[] | null {
  if (tnc.path !== "") return null;
  const found = SEARCHING.exec(tnc.describe);
  return found?.[1] === undefined ? null : found[1].split(", ");
}

function lastPacketText(tnc: TncState, nowMs: number): string {
  return tnc.stats.last_packet === null ? "no packet yet" : `last packet ${ageText(tnc.stats.last_packet, nowMs)} ago`;
}

/** The one line (with how many packets the digipeater repeated, while it is on): "Connected to /dev/ttyUSB0, last packet 2 min ago", "Searching for the radio…", "Not connected: no KISS frames on the port", "nothing heard since 02:43 (5 h)". */
export function tncStatus(tnc: TncState, nowMs: number, digipeater = false): string {
  if (tnc.state === "silent") return silentText(tnc.silent_since, nowMs);
  if (searchedPorts(tnc) !== null) return "Searching for the radio…";
  if (tnc.state === "connected") {
    const digipeated = digipeater && tnc.stats.digipeated > 0 ? `, digipeated ${tnc.stats.digipeated}` : "";
    return `Connected to ${tnc.path}, ${lastPacketText(tnc, nowMs)}${digipeated}`;
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

/** A log line of the daemon with its time (HH:MM:SS, UTC, of today or of yesterday for a time that has not come yet) in the viewer's time; any other line as it is. */
export function localLine(line: string, nowMs: number): string {
  const found = LINE_TIME.exec(line);
  if (found === null) return line;
  const today = new Date(nowMs);
  let at = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate(), Number(found[1]), Number(found[2]), Number(found[3]));
  if (at > nowMs + 60_000) at -= DAY_MS;
  return `${clockText(new Date(at).toISOString())}${line.slice(found[0].length)}`;
}
