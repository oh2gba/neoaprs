// The Bulletins tab as the page runs it: how many bulletins are new since the tab was last on show. What was seen is the time the newest text on the board was first heard, kept in the browser
// (lib/storage.ts); it moves forward while the tab is on show (the Bulletins tab is the tab in front, the panel is open and the page is visible, lib/unread.ts), so a bulletin that comes while
// the user looks at the board is seen.
import { computed, ref, watch } from "vue";
import type { Panel } from "@/composables/usePanel";
import { useVisible } from "@/composables/useVisible";
import { newCount, newestFirstHeard } from "@/lib/bulletins";
import { readStoredNumber, writeStored } from "@/lib/storage";
import { isViewingTab } from "@/lib/unread";
import type { BulletinRow } from "@/protocol/protocol";

const KEY = "bulletinsseen";

export function useBulletins(bulletins: ReadonlyMap<string, BulletinRow>, panel: Panel) {
  const visible = useVisible();
  const viewing = computed(() => isViewingTab({ tab: panel.tab.value, collapsed: panel.collapsed.value, visible: visible.value }, "bulletins"));
  const seenUpTo = ref(readStoredNumber(KEY, 0, 0, Number.MAX_SAFE_INTEGER));
  const fresh = computed(() => newCount(bulletins.values(), seenUpTo.value));

  watch(
    [viewing, () => newestFirstHeard(bulletins.values())],
    ([showing, newest]) => {
      if (!showing || newest <= seenUpTo.value) return;
      seenUpTo.value = newest;
      writeStored(KEY, String(newest));
    },
    { immediate: true },
  );

  return { fresh };
}
