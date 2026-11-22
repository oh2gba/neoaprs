// The Bulletins tab state: how many bulletins are new since the tab was last shown. The seen mark
// is the first-heard time of the newest bulletin, kept in the browser; it moves forward while the
// tab is shown, so a bulletin arriving then counts as seen. In a window with a new store, the
// first board the daemon sends counts as seen.
import { computed, ref, watch, type Ref } from "vue";
import { useViewing, type Panel } from "@/composables/usePanel";
import { newCount, newestFirstHeard } from "@/lib/bulletins";
import { seenAtStart } from "@/lib/firststart";
import { readStoredNumber, writeStored } from "@/lib/storage";
import type { BulletinRow } from "@/protocol/protocol";

const KEY = "bulletinsseen";

export function useBulletins(
  bulletins: ReadonlyMap<string, BulletinRow>,
  panel: Panel,
  loaded?: Readonly<Ref<boolean>>,
) {
  const viewing = useViewing(panel, "bulletins");
  const seenUpTo = ref(readStoredNumber(KEY, 0, 0, Number.MAX_SAFE_INTEGER));
  const fresh = computed(() => newCount(bulletins.values(), seenUpTo.value));

  // Another browser window may have moved the stored time: read it again before moving it.
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
