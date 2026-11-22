// Which tabs of the panel are in the row and which are under the More button: measured, not
// decided by a breakpoint, since the panel can be narrow on a wide screen. `box` is the tab bar,
// `probe` a hidden copy of the tabs and the More button (styles/panel.css `.tabs-probe`) whose
// children say by `data-tab="id"`, `data-more` and `data-more-count` how wide each is; `taken`
// is the width of what else is in the row, `open` the tab on show, `counts` the badges and
// `offered` the tabs the station has (lib/layout.ts `offeredTabs`). The split is lib/tabsplit.ts.
// Measured again when the bar or the probe changes size; `measure()` is for when what the probe
// holds changes.
import { computed, onBeforeUnmount, ref, watch, type Ref } from "vue";
import { TAB_IDS, type TabId } from "@/lib/layout";
import { splitTabs, type TabSizes, type TabSplit } from "@/lib/tabsplit";

const SLACK = 1;

function widthOf(probe: HTMLElement, selector: string): number {
  return probe.querySelector(selector)?.getBoundingClientRect().width ?? 0;
}

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
  offered: () => readonly TabId[] = () => TAB_IDS,
) {
  const sizes = ref<TabSizes | null>(null);
  const room = ref(0);
  let observer: ResizeObserver | undefined;

  function measure(): void {
    const outer = box.value;
    const copy = probe.value;
    // A ResizeObserver can call after the page is gone.
    if (outer === null || copy === null || !outer.isConnected) return;
    const free = outer.clientWidth - inset(outer) - taken() - SLACK;
    // Hidden: the last answer stays.
    if (free <= 0) return;
    const tabs = Object.fromEntries(TAB_IDS.map((id) => [id, widthOf(copy, `[data-tab="${id}"]`)])) as Record<TabId, number>;
    const more = widthOf(copy, "[data-more]");
    sizes.value = { tabs, more, moreCount: Math.max(0, widthOf(copy, "[data-more-count]") - more) };
    room.value = free;
  }

  const split = computed<TabSplit>(() =>
    sizes.value === null ? { shown: [...offered()], hidden: [] } : splitTabs(sizes.value, room.value, open(), counts(), offered()),
  );

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
