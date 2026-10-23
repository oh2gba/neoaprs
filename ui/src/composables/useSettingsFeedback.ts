// What the person sees of a change that applies as it is made (composables/useSettings.ts): a mark beside each key ("Saving...", then "Saved" for a moment), a line for a screen reader, and the latest change, which can be
// undone for a while.
import { getCurrentScope, onScopeDispose, reactive, ref, shallowRef } from "vue";
import type { Request } from "@/composables/useSettingsQueue";
import type { ConfigValues } from "@/protocol/protocol";

/** How long "Saved" stays beside a field, and how long the latest change can be undone. */
export const SAVED_MS = 2000;
export const UNDO_MS = 10000;

/** The latest change, to put back: `values` are the settings it replaced. */
export interface Undo {
  label: string;
  values: Record<string, string>;
  /** counts up, so that two changes of the same thing are two toasts */
  n: number;
}

export type Mark = "saving" | "saved";

export function useSettingsFeedback() {
  const marks = reactive<Record<string, Mark>>({});
  const undo = shallowRef<Undo | null>(null);
  const announcement = ref({ text: "", n: 0 });
  const savedTimers = new Map<string, ReturnType<typeof setTimeout>>();
  let undoTimer: ReturnType<typeof setTimeout> | undefined;
  let undos = 0;

  const say = (text: string): void => void (announcement.value = { text, n: announcement.value.n + 1 });

  /** The keys are on their way to the daemon. */
  function saving(keys: readonly string[]): void {
    for (const key of keys) {
      marks[key] = "saving";
      clearTimeout(savedTimers.get(key));
    }
  }

  /** The keys were not saved: no mark. */
  function dropped(keys: readonly string[]): void {
    for (const key of keys) delete marks[key];
  }

  function dismissUndo(): void {
    clearTimeout(undoTimer);
    undo.value = null;
  }

  /** The request was saved: "Saved" beside its keys for a moment, and its change to undo for a while (unless it changed nothing, or is an Undo itself, or more changes wait behind it: the toast covers the latest). */
  function saved(request: Request, now: ConfigValues, last: boolean): void {
    for (const key of request.keys) {
      marks[key] = "saved";
      clearTimeout(savedTimers.get(key));
      savedTimers.set(
        key,
        setTimeout(() => marks[key] === "saved" && delete marks[key], SAVED_MS),
      );
    }
    say("Saved");
    const changed = request.keys.some((key) => request.previous[key] !== (now.values[key] ?? ""));
    if (!changed || request.undo || !last) return;
    dismissUndo();
    undo.value = { label: request.label, values: request.previous, n: ++undos };
    undoTimer = setTimeout(() => (undo.value = null), UNDO_MS);
  }

  function dispose(): void {
    clearTimeout(undoTimer);
    for (const id of savedTimers.values()) clearTimeout(id);
  }
  if (getCurrentScope()) onScopeDispose(dispose);

  return { marks, undo, announcement, say, saving, dropped, saved, dismissUndo };
}
