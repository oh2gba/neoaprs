// Hands each message that is new since the page loaded to the alert once (lib/pagealert.ts,
// `scan`). The first state of the topic is the baseline; after a reconnect only messages above
// the highest id seen alert.
import { computed, watch, type Ref } from "vue";
import { scan } from "@/lib/pagealert";
import type { MessageRow } from "@/protocol/protocol";

export function usePageAlerts(messages: ReadonlyMap<string, MessageRow>, loaded: Ref<boolean>, announce: (fresh: MessageRow[]) => void): void {
  let mark: number | null = null;
  const rows = computed(() => (loaded.value ? [...messages.values()] : null));
  watch(
    rows,
    (now) => {
      if (now === null) return;
      const found = scan(now, mark);
      mark = found.mark;
      if (found.fresh.length > 0) announce(found.fresh);
    },
    { immediate: true },
  );
}
