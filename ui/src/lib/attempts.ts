// How many times a message is transmitted before it has failed: the count of a station (its own, else the default of the setting `messages/attempts`), and how the field for it reads what was typed.
import { MESSAGE_ATTEMPTS_DEFAULT, MESSAGE_ATTEMPTS_MAX } from "@/protocol/lists";

/** What the page knows of the attempts: the count of the stations that have one of their own, and the default for the others. */
export interface Attempts {
  own: ReadonlyMap<string, number>;
  defaultCount: number;
}

/** The count of the setting `messages/attempts`; the daemon's own default while it has not said or says something that is no count. */
export function defaultAttempts(settings: Readonly<Record<string, string>> | undefined): number {
  const count = Number(settings?.["messages/attempts"]);
  return Number.isInteger(count) && count >= 1 && count <= MESSAGE_ATTEMPTS_MAX ? count : MESSAGE_ATTEMPTS_DEFAULT;
}

/** What was typed in an attempts field: `{ count: null }` for an empty field (the default), the whole number from 1 to 10 otherwise, null for text that is no count. */
export function parseAttemptsText(text: string): { count: number | null } | null {
  const trimmed = text.trim();
  if (trimmed === "") return { count: null };
  if (!/^\d+$/.test(trimmed)) return null;
  const count = Number(trimmed);
  return count >= 1 && count <= MESSAGE_ATTEMPTS_MAX ? { count } : null;
}
