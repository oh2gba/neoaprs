// Which tabs of the panel are in the row and which are under the More button: measured, not decided by a breakpoint, since the panel beside the map can be narrow on a wide screen and a phone can be wide when held sideways.
// `box` is the tab bar, `probe` a copy of the tabs and of the More button drawn out of the way (ui/src/styles/panel.css, `.tabs-probe`: as wide as it wants, not seen, in the one size and look of the real ones) whose children say, by
// `data-tab="id"`, `data-more` and `data-more-count`, how wide each of them is, `taken` the width of what else is in the row (the Map button of a phone), `open` the tab on show and `counts` the badges. The split itself is lib/tabsplit.ts.
// Measured again whenever the bar or the probe changes size; `measure()` is for when what the probe holds changes (a badge with more digits).
import { computed, onBeforeUnmount, ref, watch, type Ref } from "vue";
import { TAB_IDS, type TabId } from "@/lib/layout";
import { splitTabs, type TabSizes, type TabSplit } from "@/lib/tabsplit";

/** What the row keeps back from the room it measures, for the rounding of the browser. */
const SLACK = 1;

function widthOf(probe: HTMLElement, selector: string): number {
  return probe.querySelector(selector)?.getBoundingClientRect().width ?? 0;
}

/** The padding of the bar at its two sides: the room of the row is what is inside it. */
function inset(box: HTMLElement): number {
  const style = getComputedStyle(box);
  return (parseFloat(style.paddingLeft) || 0) + (parseFloat(style.paddingRight) || 0);
}

export function useTabsFit(
  box: Ref<HTMLElement | null>,
  probe: Ref<HTMLElement | null>,
  taken: () => number,
  open: () => TabId,
  counts: () => Partial<Record<TabId, number>>,
) {
  const sizes = ref<TabSizes | null>(null);
  const room = ref(0);
  let observer: ResizeObserver | undefined;

  function measure(): void {
    const outer = box.value;
    const copy = probe.value;
    if (outer === null || copy === null) return;
    const free = outer.clientWidth - inset(outer) - taken() - SLACK;
    if (free <= 0) return; // hidden: the last answer stays
    const tabs = Object.fromEntries(TAB_IDS.map((id) => [id, widthOf(copy, `[data-tab="${id}"]`)])) as Record<TabId, number>;
    const more = widthOf(copy, "[data-more]");
    sizes.value = { tabs, more, moreCount: Math.max(0, widthOf(copy, "[data-more-count]") - more) };
    room.value = free;
  }

  const split = computed<TabSplit>(() => (sizes.value === null ? { shown: [...TAB_IDS], hidden: [] } : splitTabs(sizes.value, room.value, open(), counts())));

  watch(
    [box, probe],
    ([outer, copy]) => {
      observer?.disconnect();
      observer = undefined;
      if (outer === null || copy === null) return;
      measure();
      if (typeof ResizeObserver === "undefined") return;
      observer = new ResizeObserver(measure);
      observer.observe(outer);
      observer.observe(copy);
    },
    { flush: "post" },
  );
  onBeforeUnmount(() => observer?.disconnect());

  return { split, measure };
}
