// The contacts of the Email tab: the people this station mails by name and who may mail it. A contact is the gateway's "shortcut" (`name address`), kept by the gateway for the call; the page cannot ask it for the list,
// so the list is read from the station's own messages to EMAIL-2: a `name address` that was sent registers the name, a later `name R` removes it. A message the gateway rejected counts for nothing, and neither does one
// we cancelled; one that was acked, not confirmed (no ack through an iGate, though the gateway may well have it) or is still being sent does. Names are the same in any letters.
import { gatewayLine } from "@/lib/email";
import type { MessageRow } from "@/protocol/protocol";

export interface Contact {
  /** the name as it was typed (the last time it was registered) */
  name: string;
  address: string;
  /** `confirmed`: the gateway acked the registration; `sending`: it is still being sent; `unconfirmed`: its attempts ran out without an ack */
  state: "confirmed" | "sending" | "unconfirmed";
}

/** Whether a message of ours counts: it reached (or may have reached) the gateway and was not refused. */
function counts(row: MessageRow): boolean {
  return row.direction === "out" && row.state !== "rejected" && row.state !== "cancelled";
}

function stateOf(row: MessageRow): Contact["state"] {
  return row.state === "acked" ? "confirmed" : row.state === "sending" ? "sending" : "unconfirmed";
}

/** The contacts that the messages to the gateway make, by name. The oldest message counts first (a later registration of a name changes its address, a later removal drops it); the contacts come in the order of their names. */
export function contactsOf(thread: readonly MessageRow[]): Contact[] {
  const known = new Map<string, Contact>();
  for (const row of [...thread].filter(counts).sort((a, b) => a.id - b.id)) {
    const line = gatewayLine(row.text);
    if (line.kind === "add") known.set(line.name.toLowerCase(), { name: line.name, address: line.address, state: stateOf(row) });
    else if (line.kind === "remove") known.delete(line.name.toLowerCase());
  }
  return [...known.values()].sort((a, b) => a.name.localeCompare(b.name, "en", { sensitivity: "base" }));
}
