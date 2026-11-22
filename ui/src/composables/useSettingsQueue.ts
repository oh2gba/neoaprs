// Sends `set_config` one request at a time. The daemon's answer (the topic `config` again, or an
// `error`) carries no id, so the next request waits for the one out, and each answer belongs to
// exactly one request. A request the daemon does not answer in time is given up, so the queue
// cannot stay stuck.
import { computed, ref, shallowRef } from "vue";
import { t } from "@/i18n";
import type { Command } from "@/protocol/protocol";

export const ANSWER_MS = 20000;

export interface Request {
  values: Record<string, string>;
  keys: string[];
  /** Keys that show their old value again when the daemon refuses (a choice, not a typed field). */
  revert: string[];
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

  function pump(): void {
    const next = queue.value[0];
    if (inflight.value || !next) return;
    queue.value.shift();
    inflight.value = next;
    timer = setTimeout(() => give(next, t("settings.no_answer")), ANSWER_MS);
    if (!send({ cmd: "set_config", values: { ...next.values } })) give(next, t("settings.not_sent"));
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

  function enqueue(request: Request): void {
    queue.value.push(request);
    pump();
  }

  /** The value the key will have once everything sent and queued is answered. */
  function expected(key: string): string {
    for (const request of [...queue.value].reverse()) if (key in request.values) return request.values[key] ?? "";
    const out = inflight.value;
    return out && key in out.values ? (out.values[key] ?? "") : (inForce()[key] ?? "");
  }

  const waiting = (key: string): boolean => queue.value.some((request) => key in request.values);

  return { saving, inflight, enqueue, pump, release, expected, waiting, dispose: () => clearTimeout(timer) };
}
