// Hands the messages to us that are new since the page loaded to the alert, once each (lib/pagealert.ts, `scan`): what the first state of the topic holds is the baseline, and a state told again after a reconnect
// alerts only for the messages above the highest id the page has seen.
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
