// Esc closes the newest station card. Not when something else on the page takes the key (`blocked`: the setup guide, the panel with the steps of an update, which close with Esc themselves; asked before they have run), not when the
// key is for a field that is being typed in, and not when something has handled it already.
import { onBeforeUnmount, onMounted } from "vue";

export function useCardEsc(closeNewest: () => boolean, blocked: () => boolean): void {
  let wasBlocked = false;
  const first = (event: KeyboardEvent): void => {
    wasBlocked = event.key === "Escape" && blocked();
  };
  const last = (event: KeyboardEvent): void => {
    if (event.key !== "Escape" || event.defaultPrevented || wasBlocked) return;
    const target = event.target;
    if (target instanceof HTMLElement && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))) return;
    if (closeNewest()) event.preventDefault();
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
