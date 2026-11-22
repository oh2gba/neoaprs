// A computed list that is rebuilt whenever something it reads changes should keep its array
// when the items are the same, so that watchers by identity do not run for nothing.

/**
 * The old list when it holds the same items in the same order as the new one, else the new one.
 */
export function keepList<L extends readonly unknown[]>(old: L | undefined, next: L): L {
  return old !== undefined && old.length === next.length && next.every((item, i) => item === old[i]) ? old : next;
}
