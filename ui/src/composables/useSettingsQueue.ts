// The sending of `set_config` one request at a time (composables/useSettings.ts): the daemon's answer to it (the topic `config` told again, or an `error`) carries no id, so the next request waits until the one that is out
// has been answered, and each answer belongs to exactly one request. A request the daemon does not answer in time is given up, so that the queue cannot stay stuck.
import { computed, ref, shallowRef } from "vue";
import type { Command } from "@/protocol/protocol";

/** How long the daemon may take to answer a `set_config` before it is given up. */
export const ANSWER_MS = 20000;

export interface Request {
  /** key to the text to send */
  values: Record<string, string>;
  keys: string[];
  label: string;
  /** keys that show their old value again when the daemon refuses (a choice; a typed field keeps its text) */
  revert: string[];
  /** the values in force when the request was sent: what Undo sends */
  previous: Record<string, string>;
  /** the request is an Undo: it is not undone in its turn */
  undo: boolean;
}

export function useSettingsQueue(
  send: (command: Command) => boolean,
  inForce: () => Readonly<Record<string, string>>,
  failed: (request: Request, reason: string) => void,
) {
  const queue = ref<Request[]>([]);
  const inflight = shallowRef<Request | null>(null);
  const saving = computed(() => inflight.value !== null || queue.value.length > 0);
  let timer: ReturnType<typeof setTimeout> | undefined;

  /** Sends the next request if none is out. */
  function pump(): void {
    const next = queue.value[0];
    if (inflight.value || !next) return;
    queue.value.shift();
    next.previous = Object.fromEntries(next.keys.map((key) => [key, inForce()[key] ?? ""]));
    inflight.value = next;
    timer = setTimeout(() => give(next, "No answer from the daemon."), ANSWER_MS);
    if (!send({ cmd: "set_config", values: { ...next.values } })) give(next, "Not sent: there is no connection to the daemon.");
  }

  function give(request: Request, reason: string): void {
    if (inflight.value !== request) return;
    release();
    failed(request, reason);
    pump();
  }

  /** The request that is out has been answered: it is taken out of flight and given. */
  function release(): Request | null {
    clearTimeout(timer);
    const request = inflight.value;
    inflight.value = null;
    return request;
  }

  function enqueue(request: Request): void {
    queue.value.push(request);
    pump();
  }

  /** What the key will be once everything sent and queued has been answered: the last value asked for, else the one in force. */
  function expected(key: string): string {
    for (const request of [...queue.value].reverse()) if (key in request.values) return request.values[key] ?? "";
    const out = inflight.value;
    return out && key in out.values ? (out.values[key] ?? "") : (inForce()[key] ?? "");
  }

  const waiting = (key: string): boolean => queue.value.some((request) => key in request.values);

  return { saving, inflight, enqueue, pump, release, expected, waiting, dispose: () => clearTimeout(timer) };
}
