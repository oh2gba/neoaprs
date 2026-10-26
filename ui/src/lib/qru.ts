// Asking QRU for local info (the Nearby tab): the text of a request, from the word (INFO or a group) and the distance the person typed. The daemon checks it again; the number it is held to is LIMITS.qru.kmMax.
import { LIMITS } from "@/protocol/lists";

/** The distance typed, as a whole number of kilometres: null for an empty field (the servers' own range), NaN for anything that is not 1 to the most. */
export function kmOf(text: string): number | null {
  const typed = text.trim();
  if (typed === "") return null;
  const km = /^\d{1,5}$/.test(typed) ? Number(typed) : NaN;
  return km >= 1 && km <= LIMITS.qru.kmMax ? km : NaN;
}

/** Whether the distance typed is wrong (not empty, and not 1 to the most). */
export function kmWrong(text: string): boolean {
  return Number.isNaN(kmOf(text));
}

/** The text of a request: `INFO` or the group, and the distance after it when there is one; null while the distance is wrong. */
export function requestText(word: string, km: string): string | null {
  const distance = kmOf(km);
  if (Number.isNaN(distance)) return null;
  return distance === null ? word : `${word} ${distance}`;
}
