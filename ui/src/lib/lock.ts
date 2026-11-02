// What a message is besides text (its `seal`, encrypted messages): the words a bubble and a conversation row show for one that is not plain text, and the mark it carries.
import { t } from "@/i18n";
import type { MessageRow } from "@/protocol/protocol";

type Sealed = Pick<MessageRow, "seal" | "text" | "direction">;

/** The words shown for the message: its text, or for a key announcement and for an encrypted message that cannot be read here, what it is. */
export function shownText(row: Sealed): string {
  if (row.seal === "key") return t(row.direction === "out" ? "lock.key_out" : "lock.key_in");
  if (row.seal === "key_other") return t("lock.key_other");
  if (row.seal === "shut") return t("lock.shut");
  return row.text;
}

/** The mark beside the time: a padlock on an encrypted message (open: read; shut: not readable here), a key on a key announcement; null for a plain message. */
export function markOf(row: Pick<MessageRow, "seal">): { kind: "lock" | "key"; title: string } | null {
  if (row.seal === "open") return { kind: "lock", title: t("lock.mark") };
  if (row.seal === "shut") return { kind: "lock", title: t("lock.shut") };
  if (row.seal === "key" || row.seal === "key_other") return { kind: "key", title: t(row.seal === "key" ? "lock.key_mark" : "lock.key_other") };
  return null;
}
