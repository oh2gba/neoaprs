// The one clock that moves the map's marks: aircraft and ships gliding between their reports
// (lib/layers/glide.ts) and satellites between the points the daemon sent. It runs on animation
// frames while any mover is active (its layer looked at, which needs the page in front) and asks
// for no frame otherwise; each source's data is set once per step, at most every FRAME_MS.
import { getCurrentScope, onScopeDispose, watch } from "vue";

/** At most this often a step moves the marks: 20 a second. */
export const FRAME_MS = 50;

/** The motion's own clock, in milliseconds: it does not step when the device's clock is set. */
export const motionNow = (): number => performance.now();

export interface Mover {
  /** Whether it has marks to move now (read in a watcher). */
  active: () => boolean;
  /** Set its marks where they are at `nowMs`, on the motion's clock. */
  draw: (nowMs: number) => void;
}

export interface Frames {
  request: (step: () => void) => number;
  cancel: (id: number) => void;
  now: () => number;
}

const browserFrames: Frames = {
  request: (step) => requestAnimationFrame(step),
  cancel: (id) => cancelAnimationFrame(id),
  now: motionNow,
};

export function useMapMotion(movers: readonly Mover[], frames: Frames = browserFrames) {
  let id: number | null = null;
  let last = -Infinity;
  const step = (): void => {
    const now = frames.now();
    if (now - last >= FRAME_MS) {
      last = now;
      for (const mover of movers) if (mover.active()) mover.draw(now);
    }
    id = frames.request(step);
  };
  const stop = (): void => {
    if (id !== null) frames.cancel(id);
    id = null;
  };
  watch(
    () => movers.some((mover) => mover.active()),
    (on) => {
      stop();
      if (on) {
        last = -Infinity;
        id = frames.request(step);
      }
    },
    { immediate: true },
  );
  if (getCurrentScope()) onScopeDispose(stop);
  return { running: (): boolean => id !== null };
}
