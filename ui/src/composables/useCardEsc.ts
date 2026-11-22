// Esc closes all station cards and clears the selection, unless something else takes the key:
// `blocked` (checked before they run), a field with text in it, or an already handled event.
import { onBeforeUnmount, onMounted } from "vue";

const isField = (el: HTMLElement): el is HTMLInputElement | HTMLTextAreaElement => el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement;

/** True if the key belongs to the field: a field with text keeps its first Esc. */
export function keepsEsc(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && (target.isContentEditable || target.tagName === "SELECT" || (isField(target) && target.value !== ""));
}

export function useCardEsc(closeAll: () => boolean, blocked: () => boolean): void {
  let wasBlocked = false;
  const first = (event: KeyboardEvent): void => {
    wasBlocked = event.key === "Escape" && blocked();
  };
  const last = (event: KeyboardEvent): void => {
    if (event.key !== "Escape" || event.defaultPrevented || wasBlocked) return;
    if (keepsEsc(event.target)) return;
    if (closeAll()) event.preventDefault();
  };
  onMounted(() => {
    document.addEventListener("keydown", first, true);
    document.addEventListener("keydown", last);
  });
  onBeforeUnmount(() => {
    document.removeEventListener("keydown", first, true);
    document.removeEventListener("keydown", last);
  });
}
