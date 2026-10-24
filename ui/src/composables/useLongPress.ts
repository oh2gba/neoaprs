// A press that is held on a touch screen (a finger or a pen; a mouse has the right button): after `ms` without the finger moving more than a few pixels or lifting, `act` is called with where the finger is. The click that the lifting of that finger
// would make is not wanted (it would do what a tap does), so `swallowClick` is true once, for the click that follows a long press. A scroll or a second finger ends the wait.
import { getCurrentScope, onScopeDispose } from "vue";

const SLOP_PX = 10;

export function useLongPress(act: (x: number, y: number, target: HTMLElement) => void, ms = 500) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let start: { x: number; y: number } | null = null;
  let pressed = false;

  function cancel(): void {
    clearTimeout(timer);
    start = null;
  }

  /** `pointerdown` of the element that can be held. */
  function down(event: PointerEvent): void {
    cancel();
    pressed = false;
    if (event.pointerType === "mouse" || !event.isPrimary) return;
    const target = event.currentTarget;
    if (!(target instanceof HTMLElement)) return;
    start = { x: event.clientX, y: event.clientY };
    timer = setTimeout(() => {
      timer = undefined;
      if (start === null) return;
      const { x, y } = start;
      start = null;
      pressed = true;
      act(x, y, target);
    }, ms);
  }

  /** `pointermove`: a finger that has gone away from where it was put down is scrolling or dragging, not holding. */
  function move(event: PointerEvent): void {
    if (start !== null && Math.hypot(event.clientX - start.x, event.clientY - start.y) > SLOP_PX) cancel();
  }

  /** True for the one click after a long press (and then false): the click of the finger that is lifted. */
  function swallowClick(): boolean {
    const swallow = pressed;
    pressed = false;
    return swallow;
  }

  if (getCurrentScope()) onScopeDispose(cancel);
  return { down, move, up: cancel, cancel, swallowClick };
}
