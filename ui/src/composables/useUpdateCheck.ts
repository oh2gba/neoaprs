// The Check now button of the Update check group: it asks the daemon to put the question of the daily check to the version page at once (`update_check`) and shows the answer (`update_result`) beside the button for a few seconds. The button waits while the
// question is out; the daemon answers whether the daily check is on or not.
import { onScopeDispose, ref, shallowRef, watch, type Ref } from "vue";
import type { Toast } from "@/composables/useDaemon";
import { reasonOf } from "@/lib/settings";
import type { Command, UpdateResultMessage } from "@/protocol/protocol";

export const SHOWN_MS = 8000;

export interface Outcome {
  text: string;
  /** a newer version is out: the words open the panel with the steps */
  newer: boolean;
}

/** The answer in a few words. */
export function outcomeOf(message: UpdateResultMessage): Outcome {
  if (message.outcome === "newer") return { text: `${message.version} available`, newer: true };
  if (message.outcome === "current") return { text: `up to date (${message.version})`, newer: false };
  return { text: message.text || "no answer", newer: false };
}

export function useUpdateCheck(updateResult: Ref<UpdateResultMessage | null>, lastError: Ref<Toast | null>, send: (command: Command) => boolean) {
  const running = ref(false);
  const outcome = shallowRef<Outcome | null>(null);
  let timer: ReturnType<typeof setTimeout> | undefined;

  function show(next: Outcome): void {
    running.value = false;
    outcome.value = next;
    clearTimeout(timer);
    timer = setTimeout(() => (outcome.value = null), SHOWN_MS);
  }

  watch(updateResult, (message) => {
    if (message && running.value) show(outcomeOf(message));
  });
  watch(lastError, (toast) => {
    if (toast && running.value && toast.cmd === "update_check") show({ text: reasonOf(toast), newer: false });
  });

  function check(): void {
    if (running.value) return;
    clearTimeout(timer);
    outcome.value = null;
    running.value = send({ cmd: "update_check" });
  }

  onScopeDispose(() => clearTimeout(timer));
  return { running, outcome, check };
}
