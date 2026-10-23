// Whether the tabs of the panel fit in the width the panel has: measured, not decided by a breakpoint, since the panel beside the map can be narrow on a wide screen and a phone can be wide when held sideways.
// `box` is the tab bar's row, `list` the row of the tabs, `taken` the width of what else is in the row (the Map button of a phone). The row of tabs is measured by its scroll width: while the tabs do not fit the page draws it out of the way
// (ui/src/styles/panel.css, `.measuring`: as wide as it wants, not seen), so that its natural width is there to be measured in either form and the answer does not flip back and forth. Measured again whenever the row or the box changes size; `measure()` is for
// when the tabs change (a badge with more digits).
import { onBeforeUnmount, ref, watch, type Ref } from "vue";

export function useTabsFit(box: Ref<HTMLElement | null>, list: Ref<HTMLElement | null>, taken: () => number) {
  const fits = ref(true);
  let observer: ResizeObserver | undefined;

  function measure(): void {
    const outer = box.value;
    const row = list.value;
    if (outer === null || row === null) return;
    const room = outer.clientWidth - taken();
    if (room <= 0) return; // hidden: the last answer stays
    fits.value = row.scrollWidth <= room;
  }

  watch(
    [box, list],
    ([outer, row]) => {
      observer?.disconnect();
      observer = undefined;
      if (outer === null || row === null) return;
      measure();
      if (typeof ResizeObserver === "undefined") return;
      observer = new ResizeObserver(measure);
      observer.observe(outer);
      observer.observe(row);
    },
    { flush: "post" },
  );
  onBeforeUnmount(() => observer?.disconnect());

  return { fits, measure };
}
