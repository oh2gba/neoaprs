// A command whose button waits for the daemon: while it is in flight the button does not send it again (a second click, a second Enter). It lands when its answer is told (`answered` changes), when the daemon refuses it
// (an error that names the command), when the socket closes (an answer lost with it never comes) or after ANSWER_MS, so that the button cannot stay off for good.
import { computed, getCurrentScope, inject, onScopeDispose, ref, watch, type Ref, type WatchSource } from "vue";
import type { Toast } from "@/composables/useDaemon";
import { DAEMON_KEY } from "@/composables/useDaemonContext";
import type { Connection } from "@/lib/hub";

/** How long a command may wait for its answer before its button is free again. */
export const ANSWER_MS = 20_000;

export interface InFlightParts {
  lastError: Readonly<Ref<Toast | null>>;
  connection: Readonly<Ref<Connection>>;
}

/** `cmd`: the command, as an error that refuses it names it; `answered`: what the daemon tells when it was done (without it the caller says so with `land`). */
export function useInFlight(cmd: string, answered: WatchSource | null, parts: InFlightParts | null) {
  const busy = ref(false);
  let timer: ReturnType<typeof setTimeout> | undefined;

  function land(): void {
    clearTimeout(timer);
    busy.value = false;
  }

  /** Sends by `send` unless the command is in flight; true when it went. */
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

/** useInFlight with the page's context (a component mounted without one, a test, has only the answer and the time). */
export function useCommandInFlight(cmd: string, answered: WatchSource | null) {
  return useInFlight(cmd, answered, inject(DAEMON_KEY, null));
}

/** Whether the socket to the daemon is open: a box that sends is off while it is not (true without the page's context, a test). */
export function useSocketOpen(): Readonly<Ref<boolean>> {
  const context = inject(DAEMON_KEY, null);
  return computed(() => context === null || context.connection.value === "open");
}

/** Ends a wait for an answer when the socket closes: the daemon forgets a page that has gone, so the answer never comes. */
export function endWithTheSocket(connection: Readonly<Ref<Connection>> | null | undefined, end: () => void): void {
  if (connection) watch(connection, (state) => state !== "open" && end());
}
