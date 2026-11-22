// The Check now button of the Update check group: asks the daemon to put the daily check's
// question to the version page at once (`update_check`) and gives the answer (`update_result`).
// The button waits while the question is out; the daemon answers whether or not the daily check is
// on.
import { onScopeDispose, ref, shallowRef, watch, type Ref } from "vue";
import { t } from "@/i18n";
import type { Toast } from "@/composables/useDaemon";
import { endWithTheSocket } from "@/composables/useInFlight";
import type { Connection } from "@/lib/hub";
import { reasonOf } from "@/lib/settings";
import type { Command, UpdateResultMessage } from "@/protocol/protocol";

export const SHOWN_MS = 8000;

export interface Outcome {
  text: string;
  tone: string;
  newer: boolean;
}

export function outcomeOf(message: UpdateResultMessage): Outcome {
  if (message.outcome === "newer")
    return {
      text: t("settings.update.available", { version: message.version }),
      tone: "update-available",
      newer: true,
    };
  if (message.outcome === "current")
    return { text: t("settings.update.current"), tone: "update-current", newer: false };
  const id =
    message.reason === "offline"
      ? "settings.update.offline"
      : message.reason === "bad_answer"
        ? "settings.update.bad_answer"
        : "settings.update.no_answer";
  return { text: t(id), tone: "update-failed", newer: false };
}

export function useUpdateCheck(
  updateResult: Ref<UpdateResultMessage | null>,
  lastError: Ref<Toast | null>,
  send: (command: Command) => boolean,
  connection?: Readonly<Ref<Connection>>,
) {
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
    if (toast && running.value && toast.cmd === "update_check")
      show({ text: reasonOf(toast), tone: "update-failed", newer: false });
  });

  endWithTheSocket(connection, () => (running.value = false));

  function check(): void {
    if (running.value) return;
    clearTimeout(timer);
    outcome.value = null;
    running.value = send({ cmd: "update_check" });
  }

  onScopeDispose(() => clearTimeout(timer));
  return { running, outcome, check };
}
