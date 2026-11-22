// Esc ends what the Objects tab holds without saving: first a place the map waits for is given
// up, then, with the Objects tab in sight and something in its form, the selection is left and
// the form cleared, as Cancel does. Not when something else takes the key (`blocked`, asked
// before they have run), when a field outside the form has text (`keepsEsc`), or when the key is
// already handled. It runs before the station cards, which close on the Esc that is left.
import { onBeforeUnmount, onMounted } from "vue";
import { keepsEsc } from "@/composables/useCardEsc";

const inForm = (target: EventTarget | null): boolean =>
  target instanceof HTMLElement && target.tagName !== "SELECT" && target.closest(".objform") !== null;

export interface FormEscActions {
  cancelPick: () => boolean;
  closeForm: () => boolean;
  blocked: () => boolean;
}

export function useFormEsc({ cancelPick, closeForm, blocked }: FormEscActions): void {
  let wasBlocked = false;
  const first = (event: KeyboardEvent): void => {
    wasBlocked = event.key === "Escape" && blocked();
  };
  const last = (event: KeyboardEvent): void => {
    if (
      event.key !== "Escape" ||
      event.defaultPrevented ||
      wasBlocked ||
      (keepsEsc(event.target) && !inForm(event.target))
    )
      return;
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
