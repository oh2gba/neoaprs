// A press held on a touch screen: after `ms` without the finger moving more than a few pixels or
// lifting, `act` is called with the finger's place. `swallowClick` is true once, for the click
// that follows a long press. A scroll or a second finger ends the wait.
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

  function move(event: PointerEvent): void {
    if (start !== null && Math.hypot(event.clientX - start.x, event.clientY - start.y) > SLOP_PX) cancel();
  }

  function swallowClick(): boolean {
    const swallow = pressed;
    pressed = false;
    return swallow;
  }

  if (getCurrentScope()) onScopeDispose(cancel);
  return { down, move, up: cancel, cancel, swallowClick };
}
