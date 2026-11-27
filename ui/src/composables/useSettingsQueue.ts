// Sends `set_config` one request at a time, each with a number of its own that the daemon's answer
// (`saved`, or an `error`) carries back, so an answer belongs to exactly one request and another
// page's save or any other change of the settings is none. A request the daemon does not answer in
// time, or that is out when the socket closes, is given up, so the queue cannot stay stuck.
import { computed, ref, shallowRef } from "vue";
import { t } from "@/i18n";
import type { Command } from "@/protocol/protocol";

export const ANSWER_MS = 20000;

let numbered = 0;
/** The number of a new `set_config`: one count for the whole page, so that no two askers share one. */
export function saveId(): number {
  return ++numbered;
}

export interface Request {
  values: Record<string, string>;
  keys: string[];
  /** Keys that show their old value again when the daemon refuses (a choice, not a typed field). */
  revert: string[];
}

function without(request: Request, keys: readonly string[]): Request {
  const kept = (key: string): boolean => !keys.includes(key);
  return {
    values: Object.fromEntries(Object.entries(request.values).filter(([key]) => kept(key))),
    keys: request.keys.filter(kept),
    revert: request.revert.filter(kept),
  };
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
  let out = 0;

  function pump(): void {
    const next = queue.value[0];
    if (inflight.value || !next) return;
    queue.value.shift();
    inflight.value = next;
    out = saveId();
    timer = setTimeout(() => give(next, t("settings.no_answer")), ANSWER_MS);
    if (!send({ cmd: "set_config", values: { ...next.values }, id: out })) give(next, t("settings.not_sent"));
  }

  function give(request: Request, reason: string): void {
    if (inflight.value !== request) return;
    release();
    failed(request, reason);
    pump();
  }

  function release(): Request | null {
    clearTimeout(timer);
    const request = inflight.value;
    inflight.value = null;
    return request;
  }

  /** The request in flight, released, if `id` is its number (or the answer has none); null for another's. */
  function settle(id: number | null | undefined): Request | null {
    return inflight.value !== null && (id === undefined || id === null || id === out) ? release() : null;
  }

  /** Refuse the request in flight with the reason; each waiting one is then sent, and refused the same way. */
  function giveUp(reason: string): void {
    const request = inflight.value;
    if (request) give(request, reason);
  }

  /**
   * `first` puts the request ahead of every waiting one, which drop its keys (the newer value
   * wins); only the one already out stays ahead of it.
   */
  function enqueue(request: Request, first = false): void {
    if (first) {
      queue.value = queue.value.map((waiting) => without(waiting, request.keys)).filter((r) => r.keys.length > 0);
      queue.value.unshift(request);
    } else queue.value.push(request);
    pump();
  }

  /** The value the key will have once everything sent and queued is answered. */
  function expected(key: string): string {
    for (const request of [...queue.value].reverse()) if (key in request.values) return request.values[key] ?? "";
    const out = inflight.value;
    return out && key in out.values ? (out.values[key] ?? "") : (inForce()[key] ?? "");
  }

  const waiting = (key: string): boolean => queue.value.some((request) => key in request.values);

  return { saving, inflight, enqueue, pump, settle, giveUp, expected, waiting, dispose: () => clearTimeout(timer) };
}
