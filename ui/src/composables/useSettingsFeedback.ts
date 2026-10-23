// What the person is given of a change that applies as it is made (composables/useSettings.ts): a line for a screen reader ("Saved") and the latest change, which can be undone for a while. Nothing is shown beside the field: nothing on the page
// may change size or move when a setting applies.
import { getCurrentScope, onScopeDispose, ref, shallowRef } from "vue";
import type { Request } from "@/composables/useSettingsQueue";
import type { ConfigValues } from "@/protocol/protocol";

/** How long the latest change can be undone. */
export const UNDO_MS = 10000;

/** The latest change, to put back: `values` are the settings it replaced. */
export interface Undo {
  label: string;
  values: Record<string, string>;
  /** counts up, so that two changes of the same thing are two toasts */
  n: number;
}

export function useSettingsFeedback() {
  const undo = shallowRef<Undo | null>(null);
  const announcement = ref({ text: "", n: 0 });
  let undoTimer: ReturnType<typeof setTimeout> | undefined;
  let undos = 0;

  const say = (text: string): void => void (announcement.value = { text, n: announcement.value.n + 1 });

  function dismissUndo(): void {
    clearTimeout(undoTimer);
    undo.value = null;
  }

  /** The request was saved: a screen reader is told, and its change can be undone for a while (unless it changed nothing, or is an Undo itself, or more changes wait behind it: the toast covers the latest). */
  function saved(request: Request, now: ConfigValues, last: boolean): void {
    say("Saved");
    const changed = request.keys.some((key) => request.previous[key] !== (now.values[key] ?? ""));
    if (!changed || request.undo || !last) return;
    dismissUndo();
    undo.value = { label: request.label, values: request.previous, n: ++undos };
    undoTimer = setTimeout(() => (undo.value = null), UNDO_MS);
  }

  function dispose(): void {
    clearTimeout(undoTimer);
  }
  if (getCurrentScope()) onScopeDispose(dispose);

  return { undo, announcement, say, saved, dismissUndo };
}
