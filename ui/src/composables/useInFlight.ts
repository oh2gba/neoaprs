// A command whose button waits for the daemon, so a second click or Enter does not send it again.
// The wait ends when the answer arrives (`answered` changes), the daemon refuses the command (an
// error naming it), the socket closes, or after ANSWER_MS, so the button cannot stay off for good.
import { computed, getCurrentScope, inject, onScopeDispose, ref, watch, type Ref, type WatchSource } from "vue";
import type { Toast } from "@/composables/useDaemon";
import { DAEMON_KEY } from "@/composables/useDaemonContext";
import type { Connection } from "@/lib/hub";

export const ANSWER_MS = 20_000;

export interface InFlightParts {
  lastError: Readonly<Ref<Toast | null>>;
  connection: Readonly<Ref<Connection>>;
}

/**
 * `cmd`: the command, as a refusing error names it; `answered`: what the daemon sends when done.
 */
export function useInFlight(cmd: string, answered: WatchSource | null, parts: InFlightParts | null) {
  const busy = ref(false);
  let timer: ReturnType<typeof setTimeout> | undefined;

  function land(): void {
    clearTimeout(timer);
    busy.value = false;
  }

  function run(send: () => boolean): boolean {
    if (busy.value) return false;
    const sent = send();
    if (sent) {
      busy.value = true;
      clearTimeout(timer);
      timer = setTimeout(land, ANSWER_MS);
    }
    return sent;
  }

  if (answered !== null) watch(answered, land);
  if (parts !== null) {
    watch(parts.lastError, (toast) => toast?.cmd === cmd && land());
    endWithTheSocket(parts.connection, land);
  }
  if (getCurrentScope()) onScopeDispose(() => clearTimeout(timer));
  return { busy, run, land };
}

/**
 * `useInFlight` with the page's context; a component mounted without one has only the answer and
 * time.
 */
export function useCommandInFlight(cmd: string, answered: WatchSource | null) {
  return useInFlight(cmd, answered, inject(DAEMON_KEY, null));
}

/** Whether the socket to the daemon is open (true without the page's context). */
export function useSocketOpen(): Readonly<Ref<boolean>> {
  const context = inject(DAEMON_KEY, null);
  return computed(() => context === null || context.connection.value === "open");
}

/**
 * End the wait when the socket closes: the daemon forgets a gone page, so the answer never comes.
 */
export function endWithTheSocket(connection: Readonly<Ref<Connection>> | null | undefined, end: () => void): void {
  if (connection) watch(connection, (state) => state !== "open" && end());
}
