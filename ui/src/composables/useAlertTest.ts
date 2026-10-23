// The Test button of the message alert: it asks the daemon to run the alert command as it is saved (`alert_test`) and keeps the answer (`alert_result`, or the `error` of an empty command) to show under the
// field. The button waits while a test runs (the command has up to 20 s), is disabled while the field differs from what is saved (the daemon runs the saved one), and the answer goes with the next edit.
import { computed, ref, watch, type Ref } from "vue";
import type { Toast } from "@/composables/useDaemon";
import type { AlertResultMessage, Command } from "@/protocol/protocol";

export const ALERT_KEY = "messages/alert_command";

interface AlertOutcome {
  ok: boolean;
  text: string;
}

export function useAlertTest(
  alertResult: Ref<AlertResultMessage | null>,
  lastError: Ref<Toast | null>,
  send: (command: Command) => boolean,
  draft: Readonly<Record<string, string>>,
  saved: Ref<string | undefined>,
) {
  const running = ref(false);
  const result = ref<AlertOutcome | null>(null);
  const stale = computed(() => (draft[ALERT_KEY] ?? "") !== (saved.value ?? ""));

  watch(alertResult, (message) => {
    if (!message || !running.value) return;
    running.value = false;
    result.value = { ok: message.ok, text: message.text };
  });
  watch(lastError, (toast) => {
    if (!toast || !running.value) return;
    running.value = false;
    result.value = { ok: false, text: toast.text.replace(/^alert_test:\s*/, "") };
  });
  watch(
    () => draft[ALERT_KEY],
    () => (result.value = null),
  );

  function test(): void {
    if (running.value || stale.value) return;
    result.value = null;
    running.value = send({ cmd: "alert_test" });
  }

  return { running, result, stale, test };
}
