// The Skeds tab: the board is asked for (`skeds_wanted`) when the tab comes on show while the
// daemon is connected, and every 15 minutes while it stays on show, plus the count of unseen
// skeds. What was seen is the ids of the skeds on the board while the tab was on show, kept in
// the browser, the last 200. A sked of ours is never new. In a window with a new store, the first
// board sent counts as seen.
import { computed, onBeforeUnmount, ref, watch, type Ref } from "vue";
import { useViewing, type Panel } from "@/composables/usePanel";
import { seenAtStart } from "@/lib/firststart";
import { newCount } from "@/lib/skeds";
import { readStored, writeStored } from "@/lib/storage";
import type { Command, SkedsState } from "@/protocol/protocol";

const KEY = "skedsseen";
export const ASK_EVERY_MS = 15 * 60_000;
const KEPT = 200;

function stored(): Set<string> {
  try {
    const list: unknown = JSON.parse(readStored(KEY) ?? "[]");
    return new Set(Array.isArray(list) ? list.filter((id): id is string => typeof id === "string").slice(0, KEPT) : []);
  } catch {
    return new Set();
  }
}

export function useSkeds(skeds: Readonly<Ref<SkedsState | null>>, panel: Panel, send: (command: Command) => boolean, live: Readonly<Ref<boolean>>) {
  const viewing = useViewing(panel, "skeds");
  const seen = ref(stored());
  const rows = computed(() => skeds.value?.rows ?? []);
  const fresh = computed(() => newCount(rows.value, seen.value));

  let timer: ReturnType<typeof setInterval> | undefined;
  watch(
    [viewing, live],
    ([showing, open]) => {
      clearInterval(timer);
      if (!showing || !open) return;
      send({ cmd: "skeds_wanted" });
      timer = setInterval(() => void send({ cmd: "skeds_wanted" }), ASK_EVERY_MS);
    },
    { immediate: true },
  );
  onBeforeUnmount(() => clearInterval(timer));

  /**
   * Keep ids another window saw since (the stored list is read again), the board's own last, so the
   * oldest dropped are never on it.
   */
  function see(board: readonly { id: string }[]): void {
    const known = new Set([...stored(), ...seen.value]);
    const live = board.map((r) => r.id);
    if (live.every((id) => known.has(id)) && known.size === seen.value.size) return;
    const kept = [...[...known].filter((id) => !live.includes(id)), ...live].slice(-KEPT);
    seen.value = new Set(kept);
    writeStored(KEY, JSON.stringify(kept));
  }
  watch(
    [viewing, rows],
    ([showing, board]) => {
      if (showing) see(board);
    },
    { immediate: true },
  );
  seenAtStart(
    computed(() => skeds.value !== null),
    () => see(rows.value),
  );

  return { fresh };
}
