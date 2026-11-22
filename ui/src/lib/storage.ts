// What the page keeps in the browser (panel width and tab, map view): per-viewer conveniences only,
// so every access is in try/catch and the page works without it (private window, blocked data).

/** The prefix of every key the page stores. */
export const STORE_PREFIX = "NeoAPRS.";

export function readStored(key: string): string | null {
  try {
    return localStorage.getItem(STORE_PREFIX + key);
  } catch {
    return null;
  }
}

export function writeStored(key: string, value: string): void {
  try {
    localStorage.setItem(STORE_PREFIX + key, value);
  } catch {
    // Storage is unavailable; carry on without it.
  }
}

export function removeStored(key: string): void {
  try {
    localStorage.removeItem(STORE_PREFIX + key);
  } catch {
    // Storage is unavailable; nothing to remove.
  }
}

/** The stored text of `key` as a number within [min, max], else `fallback`. */
export function readStoredNumber(key: string, fallback: number, min: number, max: number): number {
  const text = readStored(key);
  if (text === null || text.trim() === "") return fallback;
  const n = Number(text);
  return Number.isFinite(n) && n >= min && n <= max ? n : fallback;
}
