// What the page remembers in the browser (the panel's width and tab, the map's view): per-viewer conveniences only, so every access is in try/catch and the page works without it
// (a private window, blocked site data).

const PREFIX = "NeoAPRS.";

export function readStored(key: string): string | null {
  try {
    return localStorage.getItem(PREFIX + key);
  } catch {
    return null;
  }
}

export function writeStored(key: string, value: string): void {
  try {
    localStorage.setItem(PREFIX + key, value);
  } catch {
    // nowhere to keep it: the page goes on
  }
}

/** The stored text of `key` as a number inside [min, max], else `fallback`. */
export function readStoredNumber(key: string, fallback: number, min: number, max: number): number {
  const text = readStored(key);
  if (text === null || text.trim() === "") return fallback;
  const n = Number(text);
  return Number.isFinite(n) && n >= min && n <= max ? n : fallback;
}
