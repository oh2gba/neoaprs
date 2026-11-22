// A computed list that is made again whenever something it reads changes should keep the array it had when its items are the same ones, so that what watches it by identity does not run for nothing.

/** The old list when it holds the same items in the same order as the new one, else the new one. */
export function keepList<L extends readonly unknown[]>(old: L | undefined, next: L): L {
  return old !== undefined && old.length === next.length && next.every((item, i) => item === old[i]) ? old : next;
}
