// Which tabs of the panel stay in the row and which go under the "More" button when the row has not room for all of them. The tabs are kept in the order of TAB_IDS (by importance), the first ones that fit stay in the row, and the tab on show
// is always one of them: when it is not among the first ones it takes the place of the last one in the row, the rest keeping their order. The widths are measured by the page (composables/useTabsFit.ts); this is the arithmetic only, so that it is tested with numbers.
import { TAB_IDS, type TabId } from "@/lib/layout";

export interface TabSizes {
  /** the width of each tab, with its count, as it is in the row */
  tabs: Record<TabId, number>;
  /** the width of the More button */
  more: number;
  /** what the count on the More button adds to its width */
  moreCount: number;
}

export interface TabSplit {
  /** the tabs in the row, in order, the tab on show last when it was brought in */
  shown: TabId[];
  /** the tabs under More, in order */
  hidden: TabId[];
}

function fit(tabs: Record<TabId, number>, space: number, open: TabId): TabSplit {
  const shown: TabId[] = [];
  let used = 0;
  for (const id of TAB_IDS) {
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
  return { shown, hidden: TAB_IDS.filter((id) => !shown.includes(id)) };
}

/**
 * The split of the tabs for a row `room` px wide. All of them when they fit; else the More button takes its width (and the width of its count, once a tab under it has one) and the rest of the room is filled from the first tab on.
 * The tab on show is in the row even when nothing else is.
 */
export function splitTabs(sizes: TabSizes, room: number, open: TabId, counts: Partial<Record<TabId, number>>): TabSplit {
  if (TAB_IDS.reduce((sum, id) => sum + sizes.tabs[id], 0) <= room) return { shown: [...TAB_IDS], hidden: [] };
  const plain = fit(sizes.tabs, room - sizes.more, open);
  if (!plain.hidden.some((id) => (counts[id] ?? 0) > 0)) return plain;
  return fit(sizes.tabs, room - sizes.more - sizes.moreCount, open);
}
