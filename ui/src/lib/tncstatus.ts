// What the TNC tab says about the radio link in plain words: one status line instead of the daemon's counters, the ports a search listens to (told in the daemon's `describe` line while it looks for the radio), and the daemon's log lines
// (which begin with the time in UTC) in the viewer's time.
import { ageText, clockText, silentText } from "@/lib/format";
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

function packetsText(tnc: TncState, nowMs: number): string {
  const { packets, last_packet } = tnc.stats;
  if (packets === 0) return "no packets yet";
  return `${packets} ${packets === 1 ? "packet" : "packets"}, last ${ageText(last_packet, nowMs)} ago`;
}

/** The one line: "Connected to /dev/ttyUSB0, 412 packets, last 2 min ago", "Searching for the radio...", "nothing heard since 02:43 (5 h)". */
export function tncStatus(tnc: TncState, nowMs: number): string {
  if (tnc.state === "silent") return silentText(tnc.silent_since, nowMs);
  if (searchedPorts(tnc) !== null) return "Searching for the radio…";
  switch (tnc.state) {
    case "connected":
      return `Connected to ${tnc.path}, ${packetsText(tnc, nowMs)}`;
    case "connecting":
      return tnc.path === "" ? "Connecting…" : `Connecting to ${tnc.path}…`;
    case "waiting":
      return tnc.path === "" ? "Waiting for the radio…" : `Waiting for ${tnc.path}…`;
    default:
      return "Not connected";
  }
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
