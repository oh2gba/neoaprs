// The conversations of the Messages tab: messages grouped by the other station, which one is open
// and how many are unseen. The seen mark is the highest message id per call, kept in the browser;
// a conversation counts as seen while the tab is shown with it open, and all count as seen in a
// window with a new store.
import { computed, ref, watch, type Ref } from "vue";
import { seenAtStart } from "@/lib/firststart";
import { conversations, newestIncomingByCall, newestIncomingId, threadOf, unreadTotal } from "@/lib/messages";
import { readStoredNumber, writeStored } from "@/lib/storage";
import type { MessageRow } from "@/protocol/protocol";

const key = (call: string): string => `read.${call}`;
const stored = (call: string): number => readStoredNumber(key(call), 0, 0, Number.MAX_SAFE_INTEGER);

/**
 * What the user has seen, by call. Another window may have marked further: a mark is compared with
 * the stored one and never written lower.
 */
export function useReadMarks() {
  const cache = new Map<string, number>();
  const changes = ref(0);
  const settled = new Set<string>();

  function readUpTo(call: string): number {
    void changes.value;
    let id = cache.get(call);
    if (id === undefined) {
      id = stored(call);
      cache.set(call, id);
    }
    return id;
  }

  function hold(call: string, held: number, inStore: number): void {
    if (held !== inStore) writeStored(key(call), String(held));
    if (held === cache.get(call)) return;
    cache.set(call, held);
    changes.value++;
  }

  function mark(call: string, id: number): void {
    const inStore = stored(call);
    hold(call, Math.max(readUpTo(call), inStore, id), inStore);
  }

  /**
   * Once per call, when its thread first has rows: a mark above every incoming id is stale
   * (database restored or newest messages deleted) and comes down to the newest id.
   */
  function settle(call: string, newest: number): void {
    if (settled.has(call)) return;
    settled.add(call);
    const inStore = stored(call);
    hold(call, Math.min(Math.max(readUpTo(call), inStore), newest), inStore);
  }

  return { readUpTo, mark, settle };
}

/**
 * `viewing`: the tab is shown; `showOverheard`: list overheard messages as conversations; `loaded`:
 * the daemon sent all messages.
 */
export function useConversations(
  messages: ReadonlyMap<string, MessageRow>,
  viewing: Ref<boolean>,
  showOverheard: Ref<boolean> = ref(false),
  loaded?: Readonly<Ref<boolean>>,
) {
  const marks = useReadMarks();
  if (loaded)
    seenAtStart(loaded, () => newestIncomingByCall(messages.values()).forEach((id, call) => marks.mark(call, id)));
  const selected = ref<string | null>(null);
  const list = computed(() => conversations(messages.values(), marks.readUpTo, showOverheard.value));
  const unread = computed(() => unreadTotal(list.value));
  const thread = computed(() => (selected.value === null ? [] : threadOf(messages.values(), selected.value)));

  watch(
    list,
    (now) => {
      if (now.length === 0) return;
      const newest = newestIncomingByCall(messages.values());
      for (const c of now) marks.settle(c.call, newest.get(c.call) ?? 0);
    },
    { immediate: true },
  );

  watch(
    [viewing, selected, () => newestIncomingId(thread.value)],
    ([showing, call, newest]) => {
      if (showing && call !== null) marks.mark(call, newest);
    },
    { immediate: true },
  );

  return { list, unread, selected, thread };
}
