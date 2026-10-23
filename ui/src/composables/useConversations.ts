// The conversations of the Messages tab: the messages grouped by the other station, which one is open, and how many messages the user has not seen. What was seen is the highest message id of
// each conversation, kept in the browser (lib/storage.ts) per call: a conversation counts as seen while the Messages tab is on show with it open.
import { computed, ref, watch, type Ref } from "vue";
import { conversations, newestIncomingId, threadOf, unreadTotal } from "@/lib/messages";
import { readStoredNumber, writeStored } from "@/lib/storage";
import type { MessageRow } from "@/protocol/protocol";

const key = (call: string): string => `read.${call}`;

/** What the user has seen, by call. Reading it in a computed value makes that value follow `mark`. */
export function useReadMarks() {
  const cache = new Map<string, number>();
  const changes = ref(0);

  function readUpTo(call: string): number {
    void changes.value;
    let id = cache.get(call);
    if (id === undefined) {
      id = readStoredNumber(key(call), 0, 0, Number.MAX_SAFE_INTEGER);
      cache.set(call, id);
    }
    return id;
  }

  function mark(call: string, id: number): void {
    if (id <= readUpTo(call)) return;
    cache.set(call, id);
    writeStored(key(call), String(id));
    changes.value++;
  }

  return { readUpTo, mark };
}

/** `viewing` is true while the Messages tab is on show; `showOverheard` lists the messages we only heard as conversations of their own. */
export function useConversations(messages: ReadonlyMap<string, MessageRow>, viewing: Ref<boolean>, showOverheard: Ref<boolean> = ref(false)) {
  const marks = useReadMarks();
  const selected = ref<string | null>(null);
  const list = computed(() => conversations(messages.values(), marks.readUpTo, showOverheard.value));
  const unread = computed(() => unreadTotal(list.value));
  const thread = computed(() => (selected.value === null ? [] : threadOf(messages.values(), selected.value)));

  watch(
    [viewing, selected, () => newestIncomingId(thread.value)],
    ([showing, call, newest]) => {
      if (showing && call !== null) marks.mark(call, newest);
    },
    { immediate: true },
  );

  return { list, unread, selected, thread };
}
