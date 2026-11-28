// The chat of the HF tests tab (topics `chat` and `chat_lines`): the lines in the order they were
// said, how many of others came since the newest seen, and the daemon's rule for a line's text
// (neoaprs/chat.py `clean_text`, held to the same vectors), so that Send is off for a line the daemon
// would find empty.
import type { ChatLineRow } from "@/protocol/protocol";
import { LIMITS } from "@/protocol/lists";

/** The white space of Unicode, made one plain space (neoaprs/skeds.py NOTE_SPACE). */
const SPACES = /[\t-\r \x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+/gu;
/** What a line loses: the control, format, private-use, surrogate and unassigned characters. */
const DROPPED = /\p{C}/gu;
/** A run of combining marks past the third, which would paint over the lines beside it. */
const MARKS = /(\p{M}{3})\p{M}+/gu;

/** The line as the daemon and the server make it: one line, at most LIMITS.chat.textMax characters. */
export function chatText(text: string): string {
  const kept = text
    .replace(SPACES, " ")
    .replace(DROPPED, "")
    .replace(MARKS, "$1")
    .replace(/ {2,}/g, " ")
    .replace(/^ +| +$/g, "");
  return [...kept]
    .slice(0, LIMITS.chat.textMax)
    .join("")
    .replace(/^ +| +$/g, "");
}

/** The lines oldest first (by the server's id). */
export function chatLines(rows: Iterable<ChatLineRow>): ChatLineRow[] {
  return [...rows].sort((a, b) => a.id - b.id);
}

/** The lines of others newer than `seen`; none before the first mark. */
export function unseenCount(rows: Iterable<ChatLineRow>, seen: number | null): number {
  if (seen === null) return 0;
  let n = 0;
  for (const row of rows) if (row.id > seen && !row.ours) n += 1;
  return n;
}

/** The newest id of the lines, or null for none. */
export function newestId(rows: Iterable<ChatLineRow>): number | null {
  let top: number | null = null;
  for (const row of rows) if (top === null || row.id > top) top = row.id;
  return top;
}
