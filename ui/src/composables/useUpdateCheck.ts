// The Check now button of the Update check group: it asks the daemon to put the question of the daily check to the version page at once (`update_check`) and gives the answer (`update_result`) for the form to say. The button waits while the
// question is out; the daemon answers whether the daily check is on or not.
import { onScopeDispose, ref, shallowRef, watch, type Ref } from "vue";
import { t } from "@/i18n";
import type { Toast } from "@/composables/useDaemon";
import { reasonOf } from "@/lib/settings";
import type { Command, UpdateResultMessage } from "@/protocol/protocol";

export const SHOWN_MS = 8000;

export interface Outcome {
  text: string;
  /** the class that colours the words: the page's ok, warn or accent */
  tone: string;
  /** a newer version is out: the words open the panel with the steps */
  newer: boolean;
}

/** The answer in a few words. */
export function outcomeOf(message: UpdateResultMessage): Outcome {
  if (message.outcome === "newer") return { text: t("settings.update.available", { version: message.version }), tone: "update-available", newer: true };
  if (message.outcome === "current") return { text: t("settings.update.current"), tone: "update-current", newer: false };
  return { text: message.text || t("settings.update.no_answer"), tone: "update-failed", newer: false };
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
    if (toast && running.value && toast.cmd === "update_check") show({ text: reasonOf(toast), tone: "update-failed", newer: false });
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
