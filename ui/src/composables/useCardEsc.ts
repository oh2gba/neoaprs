// Esc closes the station cards, all of them at once (and so clears the selection: the rows and the markers are not marked any more). Not when something else on the page takes the key (`blocked`: the setup guide, the panel with the steps of an update, which close with Esc themselves; asked before they have run), not when the
// key is for a field that has text in it (it is for the field: the filter box of the Stations table clears itself on the first Esc and, empty, lets the next one through), and not when something has handled it already.
import { onBeforeUnmount, onMounted } from "vue";

const isField = (el: HTMLElement): el is HTMLInputElement | HTMLTextAreaElement => el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement;

export function useCardEsc(closeAll: () => boolean, blocked: () => boolean): void {
  let wasBlocked = false;
  const first = (event: KeyboardEvent): void => {
    wasBlocked = event.key === "Escape" && blocked();
  };
  const last = (event: KeyboardEvent): void => {
    if (event.key !== "Escape" || event.defaultPrevented || wasBlocked) return;
    const target = event.target;
    if (target instanceof HTMLElement && (target.isContentEditable || target.tagName === "SELECT" || (isField(target) && target.value !== ""))) return;
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
