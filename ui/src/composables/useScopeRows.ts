// The rows of the HF radio's waterfall (binary frames, lib/scoperow.ts) are not state: each is told to the panes that draw them and kept by none, so a pane listens (`onScopeRow`, in the page's context) while it has the scope open.
import type { ScopeRow } from "@/lib/scoperow";

export function useScopeRows() {
  const listeners = new Set<(row: ScopeRow) => void>();
  /** Listens to the rows; the function it returns stops it. */
  const onScopeRow = (listener: (row: ScopeRow) => void): (() => void) => {
    listeners.add(listener);
    return () => void listeners.delete(listener);
  };
  /** A row came: the store's `hfScopeRow`. */
  const hfScopeRow = (row: ScopeRow): void => listeners.forEach((listener) => listener(row));
  return { onScopeRow, hfScopeRow };
}
