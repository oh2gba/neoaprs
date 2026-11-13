// The Skeds tab as the page runs it: the board is asked for (`skeds_wanted`) when the tab comes on show while the daemon is connected (and so when a page loads with the tab in front, once the socket is open, and again after a reconnect) and every 15
// minutes while it stays on show (the daemon reads at most that often whatever the page asks), and the count of the skeds
// not seen yet. What was seen is the ids of the skeds that were on the board while the tab was on show, kept in the browser (lib/storage.ts), the last 200 of them. A sked of ours is never new. The tab is on show when
// it is the tab in front, the panel is open and the page is visible (lib/unread.ts), as for the bulletins.
import { computed, onBeforeUnmount, ref, watch, type Ref } from "vue";
import type { Panel } from "@/composables/usePanel";
import { useVisible } from "@/composables/useVisible";
import { newCount } from "@/lib/skeds";
import { readStored, writeStored } from "@/lib/storage";
import { isViewingTab } from "@/lib/unread";
import type { Command, SkedsState } from "@/protocol/protocol";

const KEY = "skedsseen";
/** How often the page asks again while the tab stays on show. */
export const ASK_EVERY_MS = 15 * 60_000;
/** The most ids kept: the board holds 100 skeds. */
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
  const visible = useVisible();
  const viewing = computed(() => isViewingTab({ tab: panel.tab.value, collapsed: panel.collapsed.value, visible: visible.value }, "skeds"));
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

  watch(
    [viewing, rows],
    ([showing, board]) => {
      if (!showing || board.every((r) => seen.value.has(r.id))) return;
      seen.value = new Set([...seen.value, ...board.map((r) => r.id)].slice(-KEPT));
      writeStored(KEY, JSON.stringify([...seen.value]));
    },
    { immediate: true },
  );

  return { fresh };
}
