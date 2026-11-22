// Which tabs stay in the row and which go under the "More" button when the row cannot hold all. The
// offered tabs (lib/layout.ts `offeredTabs`) keep their order, the first ones that fit stay, and
// the tab on show is always in the row: if it is not among the first it takes the last place.
// Widths are measured by composables/useTabsFit.ts; this is only the arithmetic.
import { TAB_IDS, type TabId } from "@/lib/layout";

export interface TabSizes {
  /** The width of each tab, with its count, as in the row. */
  tabs: Record<TabId, number>;
  /** The width of the More button. */
  more: number;
  /** What the count on the More button adds to its width. */
  moreCount: number;
}

export interface TabSplit {
  /** The tabs in the row, in order, the tab on show last when it was brought in. */
  shown: TabId[];
  /** The tabs under More, in order. */
  hidden: TabId[];
}

function fit(tabs: Record<TabId, number>, space: number, open: TabId, order: readonly TabId[]): TabSplit {
  const shown: TabId[] = [];
  let used = 0;
  for (const id of order) {
    if (used + tabs[id] > space) break;
    shown.push(id);
    used += tabs[id];
  }
  if (!shown.includes(open)) {
    for (let last = shown[shown.length - 1]; last !== undefined && used + tabs[open] > space; last = shown[shown.length - 1]) {
      shown.pop();
      used -= tabs[last];
    }
    shown.push(open);
  }
  return { shown, hidden: order.filter((id) => !shown.includes(id)) };
}

/**
 * The split of the tabs for a row `room` px wide. All stay when they fit; else the More button
 * takes its width (and its count's, once a tab under it has one) and the rest is filled from the
 * first tab on. The tab on show is always in the row. `order` is the offered tabs (all unless
 * said).
 */
export function splitTabs(sizes: TabSizes, room: number, open: TabId, counts: Partial<Record<TabId, number>>, order: readonly TabId[] = TAB_IDS): TabSplit {
  if (order.reduce((sum, id) => sum + sizes.tabs[id], 0) <= room) return { shown: [...order], hidden: [] };
  const plain = fit(sizes.tabs, room - sizes.more, open, order);
  if (!plain.hidden.some((id) => (counts[id] ?? 0) > 0)) return plain;
  return fit(sizes.tabs, room - sizes.more - sizes.moreCount, open, order);
}
