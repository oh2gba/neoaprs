// The delivery chain of a message of ours (the `attempts_detail` of its row), as the chips the thread shows: "you → OH2RCH-2 → OH2RDG → OH2CUB-7". A hop is green with a check when a copy of our own packet was heard with that hop used, grey with a "?"
// when none was (a digipeater we never hear direct cannot be confirmed from here), blue with "internet" when it was seen only in a copy an iGate gated back; the recipient is green on the ack, red on failure, grey while it waits.
import { clockText, dateTimeText } from "@/lib/format";
import type { AttemptRow, HopRow, MessageRow } from "@/protocol/protocol";

export type ChipKind = "you" | "heard" | "internet" | "unheard" | "acked" | "failed" | "waiting";

export interface Chip {
  kind: ChipKind;
  /** the call, or "you" */
  text: string;
  /** what follows the call: a check, a cross, "?" or "internet"; empty for none */
  mark: string;
  /** what hovering over the chip says */
  title: string;
}

const MARKER = /^(TCPIP|TCPXX|NOGATE|RFONLY|NOTCP|qA)/;
const ALIAS = /^(WIDE|TRACE|RELAY|ECHO|GATE|TEMP|TRACK|SAR)\d?(-\d{1,2})?$/;

/** Whether a call is an alias of a path (WIDE1-1): any digipeater may answer it, so there is no one station to hear. */
export function isAlias(call: string): boolean {
  return ALIAS.test(call);
}

/** Whether a path element is a marker for the iGates and the internet (RFONLY, NOGATE, TCPIP, TCPXX, a q-construct such as qAR) and no hop: nothing repeats it, so the chain has no chip for it. */
export function isMarker(call: string): boolean {
  return MARKER.test(call);
}

/** "1 attempt", "3 attempts". */
export function attemptsText(count: number): string {
  return `${count} ${count === 1 ? "attempt" : "attempts"}`;
}

function hopChip(hop: HopRow, heardDirect: ReadonlySet<string>): Chip {
  if (hop.heard) {
    const at = hop.heard_at === null ? "" : ` ${dateTimeText(hop.heard_at)}`;
    return { kind: "heard", text: hop.call, mark: "✓", title: `heard${at}${hop.by_internet ? ", and over the internet" : ""}` };
  }
  if (hop.by_internet) {
    const at = hop.heard_at === null ? "" : ` ${clockText(hop.heard_at)}`;
    return { kind: "internet", text: hop.call, mark: "internet", title: `seen${at} in a copy gated back over the internet, not heard here` };
  }
  const beyond = !isAlias(hop.call) && !heardDirect.has(hop.call);
  return { kind: "unheard", text: hop.call, mark: "?", title: beyond ? "not heard here: beyond what this station can hear" : "not heard" };
}

function recipientChip(row: MessageRow, attempt: AttemptRow, latest: boolean): Chip {
  const text = row.to_call;
  if (attempt.acked) return { kind: "acked", text, mark: "✓", title: row.acked_at === null ? "acked" : `acked ${dateTimeText(row.acked_at)}` };
  if (latest && (row.state === "failed" || row.state === "rejected")) {
    return { kind: "failed", text, mark: "✗", title: row.state === "failed" ? `no answer after ${row.attempts} attempts` : "rejected" };
  }
  const waiting = !latest
    ? "no ack after this attempt"
    : row.state === "unconfirmed"
      ? "sent, no ack expected"
      : row.state === "cancelled"
        ? "cancelled"
        : "waiting for the ack";
  return { kind: "waiting", text, mark: "", title: waiting };
}

/** The chips of one attempt: us, each digipeater of its path (RFONLY, NOGATE, TCPIP and the like are not hops), a chip for a copy that came back over the internet when no hop shows it, and the recipient. `latest` is the newest attempt of the message, the one a failure is told on. */
export function chainOf(row: MessageRow, attempt: AttemptRow, latest: boolean, heardDirect: ReadonlySet<string> = new Set()): Chip[] {
  const chips: Chip[] = [{ kind: "you", text: "you", mark: "", title: `sent ${dateTimeText(attempt.sent_at)}` }];
  chips.push(...attempt.hops.filter((hop) => !isMarker(hop.call)).map((hop) => hopChip(hop, heardDirect)));
  if (attempt.internet !== null && !attempt.hops.some((hop) => hop.by_internet)) {
    chips.push({ kind: "internet", text: "internet", mark: "", title: `a copy came back over the internet, by ${attempt.internet}` });
  }
  chips.push(recipientChip(row, attempt, latest));
  return chips;
}
