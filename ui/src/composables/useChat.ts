// The chat of the HF tests tab, held by the page shell so that a line being written survives a
// change of tab: the lines oldest first, the state, the text being written and Send, and the count of
// lines of others not seen yet. A line is seen while the tab is on show; the newest id seen is kept in
// the browser, and in a browser with none the first lines count as seen. Send keeps the text until
// the daemon's answer is the line itself (`ours`); a refusal or a closed socket leaves it as it was.
// New lines of others (`chat_fresh`, which the daemon sends only while its notification is on) go to
// the browser's alert.
import { computed, onScopeDispose, getCurrentScope, ref, watch, type Ref } from "vue";
import { useViewing, type Panel } from "@/composables/usePanel";
import type { Toast } from "@/composables/useDaemon";
import { chatLines, chatText, newestId, unseenCount } from "@/lib/chat";
import type { Connection } from "@/lib/hub";
import { readStored, writeStored } from "@/lib/storage";
import type { ChatFreshMessage, ChatLineRow, ChatState, Command } from "@/protocol/protocol";

const KEY = "chatseen";
/** The longest a line waits for its answer before Send is offered again; the text stays. */
const SAY_WAIT_MS = 20_000;

interface ChatParts {
  chatState: Readonly<Ref<ChatState | null>>;
  chatLines: Readonly<Ref<ReadonlyMap<string, ChatLineRow> | null>>;
  chatFresh: Readonly<Ref<ChatFreshMessage | null>>;
  lastError: Readonly<Ref<Toast | null>>;
  connection: Readonly<Ref<Connection>>;
  send: (command: Command) => boolean;
}

function storedSeen(): number | null {
  const kept = Number(readStored(KEY));
  return Number.isSafeInteger(kept) && kept > 0 ? kept : null;
}

export function useChat(parts: ChatParts, panel: Panel, announce: (fresh: ChatFreshMessage) => void) {
  const viewing = useViewing(panel, "skeds");
  const lines = computed(() => chatLines(parts.chatLines.value?.values() ?? []));
  const state = computed(() => parts.chatState.value?.state ?? null);
  const draft = ref("");
  const busy = ref(false);
  let pending: string | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const seen = ref<number | null>(storedSeen());
  function see(): void {
    const top = newestId(lines.value);
    const kept = storedSeen();
    const mark = Math.max(top ?? 0, kept ?? 0, seen.value ?? 0);
    if (mark > 0 && mark !== seen.value) {
      seen.value = mark;
      writeStored(KEY, String(mark));
    }
  }
  watch(
    [viewing, lines],
    ([showing, now]) => {
      if (parts.chatLines.value === null) return;
      if (showing || (seen.value === null && now.length > 0)) see();
    },
    { immediate: true },
  );
  const unread = computed(() => (viewing.value ? 0 : unseenCount(lines.value, seen.value)));

  function land(): void {
    clearTimeout(timer);
    busy.value = false;
    pending = null;
  }

  /** Send the line; false when there is nothing to say, a line is on its way, or the socket is closed. */
  function say(): boolean {
    const text = chatText(draft.value);
    if (text === "" || busy.value || !parts.send({ cmd: "chat_say", text: draft.value })) return false;
    pending = text;
    busy.value = true;
    clearTimeout(timer);
    timer = setTimeout(land, SAY_WAIT_MS);
    return true;
  }

  watch(lines, (now) => {
    if (pending === null) return;
    const said = pending;
    if (now.some((row) => row.ours && row.text === said)) {
      if (chatText(draft.value) === said) draft.value = "";
      land();
    }
  });
  watch(parts.lastError, (toast) => toast?.cmd === "chat_say" && land());
  watch(parts.connection, (now) => now !== "open" && land());
  watch(parts.chatFresh, (message) => message && announce(message));
  if (getCurrentScope()) onScopeDispose(() => clearTimeout(timer));

  return { lines, state, draft, busy, unread, say };
}

export type ChatModel = ReturnType<typeof useChat>;
