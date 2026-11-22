// The open (i) note (components/InfoTip.vue): one for the whole page, so opening a note closes the
// previous one.
import { shallowRef } from "vue";

export const openTip = shallowRef<string | null>(null);

let count = 0;
/**
 * A unique id for a note (our own counter: two pages mounted in one test would share what Vue's
 * useId gives).
 */
export function newTipId(): string {
  count += 1;
  return `infotip-${count}`;
}

export interface Box {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

/**
 * Where an (i)'s note goes, in window coordinates (`position: fixed`, so no panel, pane or map
 * clips it): under the (i) with its right edge at the (i)'s right edge, or its left edge at the
 * (i)'s when that leaves less room on the left, moved sideways to fit in the window, and above the
 * (i) when there is less room below than above and it does not fit below. `size` is the note's
 * width and height, `view` the window's, `margin` the gap kept to its edges. A note wider than the
 * window is as wide as it.
 */
export function placeNote(
  trigger: Box,
  size: { width: number; height: number },
  view: { width: number; height: number },
  margin = 8,
  gap = 4,
): { left: number; top: number; width: number } {
  const width = Math.min(size.width, view.width - 2 * margin);
  const toRight = trigger.right - width;
  const left = Math.max(margin, Math.min(toRight, view.width - margin - width));
  const below = view.height - margin - (trigger.bottom + gap);
  const above = trigger.top - gap - margin;
  const flip = size.height > below && above > below;
  const top = flip ? Math.max(margin, trigger.top - gap - size.height) : trigger.bottom + gap;
  return { left, top, width };
}
