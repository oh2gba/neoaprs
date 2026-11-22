// The Bulletins tab as the page runs it: how many bulletins are new since the tab was last on show. What was seen is the time the newest text on the board was first heard, kept in the browser
// (lib/storage.ts); it moves forward while the tab is on show (the Bulletins tab is the tab in front, the panel is open and the page is visible, lib/unread.ts), so a bulletin that comes while
// the user looks at the board is seen. In a window whose store was new, the board the daemon tells first is seen (lib/firststart.ts).
import { computed, ref, watch, type Ref } from "vue";
import { useViewing, type Panel } from "@/composables/usePanel";
import { newCount, newestFirstHeard } from "@/lib/bulletins";
import { seenAtStart } from "@/lib/firststart";
import { readStoredNumber, writeStored } from "@/lib/storage";
import type { BulletinRow } from "@/protocol/protocol";

const KEY = "bulletinsseen";

/** `loaded`: the daemon has told the bulletins whole. */
export function useBulletins(bulletins: ReadonlyMap<string, BulletinRow>, panel: Panel, loaded?: Readonly<Ref<boolean>>) {
  const viewing = useViewing(panel, "bulletins");
  const seenUpTo = ref(readStoredNumber(KEY, 0, 0, Number.MAX_SAFE_INTEGER));
  const fresh = computed(() => newCount(bulletins.values(), seenUpTo.value));

  /** What another window of the browser saw since is kept: the stored time is read again before it is moved. */
  function see(newest: number): void {
    const inStore = readStoredNumber(KEY, 0, 0, Number.MAX_SAFE_INTEGER);
    seenUpTo.value = Math.max(seenUpTo.value, inStore, newest);
    if (seenUpTo.value > inStore) writeStored(KEY, String(seenUpTo.value));
  }
  watch(
    [viewing, () => newestFirstHeard(bulletins.values())],
    ([showing, newest]) => {
      if (showing) see(newest);
    },
    { immediate: true },
  );
  if (loaded) seenAtStart(loaded, () => see(newestFirstHeard(bulletins.values())));

  return { fresh };
}
