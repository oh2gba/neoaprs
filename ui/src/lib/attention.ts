// "Go to this setting": after a tab is opened, bring the group a control is in into view, flash it once and move the keyboard to the control. One helper for every link that leads to a setting (the marks of the header, a hint that
// says "Settings → Radio → RX only"). The flash is the soft accent of the palette (`.attend` in styles/settings.css), fading out in ATTEND_MS; with reduced motion it is the same colour held for that long, with no animation.
import { nextTick } from "vue";

/** How long the group is highlighted. */
export const ATTEND_MS = 1500;
/** How long the helper waits for the control to be on the page (the tab may need a moment to be drawn). */
const WAIT_MS = 600;

/** The element that is flashed for a control: the group (fieldset) it is in, else the row it is in, else itself. */
const flashed = (control: HTMLElement): HTMLElement => control.closest<HTMLElement>("fieldset") ?? control.closest<HTMLElement>(".field") ?? control;

/** Scrolls the group of the control with this id into view, flashes it and focuses the control. Gives up quietly when the control does not show up. `root` is where to look (the document). Returns whether it found the control. */
export async function attend(controlId: string, root: Document = document): Promise<boolean> {
  await nextTick();
  const until = Date.now() + WAIT_MS;
  let control = root.getElementById(controlId);
  while (control === null && Date.now() < until) {
    await new Promise((resolve) => setTimeout(resolve, 30));
    control = root.getElementById(controlId);
  }
  if (control === null) return false;
  const group = flashed(control);
  group.scrollIntoView?.({ block: "center", behavior: matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  group.classList.remove("attend");
  void group.offsetWidth; // (so that a second press starts the flash again)
  group.classList.add("attend");
  setTimeout(() => group.classList.remove("attend"), ATTEND_MS);
  control.focus({ preventScroll: true });
  return true;
}
