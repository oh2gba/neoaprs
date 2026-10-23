// The (i) note that is open (components/InfoTip.vue): one for the whole page, so that opening a note closes the one that was open.
import { shallowRef } from "vue";

export const openTip = shallowRef<string | null>(null);

let count = 0;
/** An id for a note, different from every other (a counter of our own: two pages mounted in one test would share what Vue's useId gives). */
export function newTipId(): string {
  count += 1;
  return `infotip-${count}`;
}
