// Esc on the page ends what the Objects tab holds, without saving: a place that the map is waiting for is given up first (the My station tab's and the form's), and then, with the Objects tab in sight and something in its form (an object selected, or text typed), the selection is left and the form cleared, as Cancel does. Not when something
// else on the page takes the key (`blocked`: the setup guide, the panel with the steps of an update; asked before they have run), not when the key is for a field outside the form that has text in it (`keepsEsc`: it keeps its first Esc; the fields of the form itself have nothing to clear with it, so Esc there clears the form), and not when something has
// handled it already (a list that is open, the symbol picker). It handles the key before the station cards do (they close on the Esc that is left), so it is set up before them.
import { onBeforeUnmount, onMounted } from "vue";
import { keepsEsc } from "@/composables/useCardEsc";

/** The key was pressed in a field of the form that this Esc clears (the Objects tab's). */
const inForm = (target: EventTarget | null): boolean => target instanceof HTMLElement && target.tagName !== "SELECT" && target.closest(".objform") !== null;

export interface FormEscActions {
  /** a place is waited for on the map: give it up; true when there was one */
  cancelPick: () => boolean;
  /** the form is in sight and holds something: clear it; true when it did */
  closeForm: () => boolean;
  /** something else takes the key */
  blocked: () => boolean;
}

export function useFormEsc({ cancelPick, closeForm, blocked }: FormEscActions): void {
  let wasBlocked = false;
  const first = (event: KeyboardEvent): void => {
    wasBlocked = event.key === "Escape" && blocked();
  };
  const last = (event: KeyboardEvent): void => {
    if (event.key !== "Escape" || event.defaultPrevented || wasBlocked || (keepsEsc(event.target) && !inForm(event.target))) return;
    if (cancelPick() || closeForm()) event.preventDefault();
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
