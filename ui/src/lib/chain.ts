// The delivery chain of a message of ours (the `attempts_detail` of its row), as the chips the thread shows: "you → OH2RCH-2 → OH2RDG → OH2CUB-7". A hop is green with a check when a copy of our own packet was heard with that hop used, grey with a "?"
// when none was (a digipeater we never hear direct cannot be confirmed from here), blue with "internet" when it was seen only in a copy an iGate gated back; the recipient is green on the ack, red on failure, grey while it waits.
import { t } from "@/i18n";
import { clockText, dateTimeText } from "@/lib/format";
import type { AttemptRow, HopRow, MessageRow } from "@/protocol/protocol";

type ChipKind = "you" | "heard" | "internet" | "unheard" | "acked" | "failed" | "waiting";

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

function hopChip(hop: HopRow, heardDirect: ReadonlySet<string>): Chip {
  const internet = hop.by_internet ? "yes" : "no";
  if (hop.heard) {
    const title = hop.heard_at === null ? t("chain.heard", { internet }) : t("chain.heard_at", { internet, time: dateTimeText(hop.heard_at) });
    return { kind: "heard", text: hop.call, mark: "✓", title };
  }
  if (hop.by_internet) {
    const title = hop.heard_at === null ? t("chain.seen_internet") : t("chain.seen_internet_at", { time: clockText(hop.heard_at) });
    return { kind: "internet", text: hop.call, mark: t("chain.internet"), title };
  }
  const beyond = !isAlias(hop.call) && !heardDirect.has(hop.call);
  return { kind: "unheard", text: hop.call, mark: "?", title: beyond ? t("chain.not_heard_beyond") : t("chain.not_heard") };
}

function recipientChip(row: MessageRow, attempt: AttemptRow, latest: boolean, mail: boolean): Chip {
  const text = row.to_call;
  if (attempt.acked) {
    const title = row.acked_at === null ? t("messages.mark.acked") : t("messages.mark.acked_at", { time: dateTimeText(row.acked_at) });
    return { kind: "acked", text, mark: "✓", title };
  }
  if (latest && mail && row.state === "failed") return { kind: "waiting", text, mark: "", title: t("chain.mail_unconfirmed") };
  if (latest && (row.state === "failed" || row.state === "rejected")) {
    return { kind: "failed", text, mark: "✗", title: row.state === "failed" ? t("messages.state.failed", { n: row.attempts }) : t("messages.state.rejected") };
  }
  const waiting = !latest
    ? t("chain.no_ack_after")
    : row.state === "unconfirmed"
      ? t("messages.mark.no_ack_expected")
      : row.state === "cancelled"
        ? t("messages.mark.cancelled")
        : t("chain.waiting_for_ack");
  return { kind: "waiting", text, mark: "", title: waiting };
}

/** The chips of one attempt: us, each digipeater of its path (RFONLY, NOGATE, TCPIP and the like are not hops), a chip for a copy that came back over the internet when no hop shows it, and the recipient. `latest` is the newest attempt of the message, the one a failure is told on. */
export function chainOf(row: MessageRow, attempt: AttemptRow, latest: boolean, heardDirect: ReadonlySet<string> = new Set(), mail = false): Chip[] {
  const chips: Chip[] = [{ kind: "you", text: t("chain.you"), mark: "", title: t("chain.sent", { time: dateTimeText(attempt.sent_at) }) }];
  chips.push(...attempt.hops.filter((hop) => !isMarker(hop.call)).map((hop) => hopChip(hop, heardDirect)));
  if (attempt.internet !== null && !attempt.hops.some((hop) => hop.by_internet)) {
    chips.push({ kind: "internet", text: t("chain.internet"), mark: "", title: t("chain.copy_back", { by: attempt.internet }) });
  }
  chips.push(recipientChip(row, attempt, latest, mail)); // (mail: a gateway whose ack may never reach us is not failed)
  return chips;
}
