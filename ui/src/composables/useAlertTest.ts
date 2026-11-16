// The Test button of the message alert: it asks the daemon to run the alert command as it is saved (`alert_test`) and keeps the answer (`alert_result`, or the `error` of an empty command) for the form to say. The button waits while a test runs (the command has up to 20 s), is disabled while the field differs from what is saved (the daemon runs the saved one), and the answer goes with the next edit.
import { computed, ref, watch, type Ref } from "vue";
import { t } from "@/i18n";
import type { Toast } from "@/composables/useDaemon";
import { reasonOf } from "@/lib/settings";
import type { AlertResultMessage, Command } from "@/protocol/protocol";

export const ALERT_KEY = "messages/alert_command";

/** How the command ended, in words: it ran, its exit code (with the first line it wrote to stderr, its own words), that it ran out of time, that it could not start; an outcome the page has no words for
 * (a daemon of another build) by whether it went well. */
export function outcomeText(message: AlertResultMessage): string {
  if (message.outcome === "ran") return t("settings.alert_test.ran");
  if (message.outcome === "timeout") return t("settings.alert_test.timeout", { seconds: message.seconds });
  if (message.outcome === "no_start") return t("settings.alert_test.no_start");
  if (message.outcome !== "exit") return t(message.ok ? "settings.alert_test.ran" : "error.failed");
  return message.line
    ? t("settings.alert_test.exit_line", { status: message.status, line: message.line })
    : t("settings.alert_test.exit", { status: message.status });
}

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
    result.value = { ok: message.ok, text: outcomeText(message) };
  });
  watch(lastError, (toast) => {
    if (!toast || !running.value || toast.cmd !== "alert_test") return;
    running.value = false;
    result.value = { ok: false, text: reasonOf(toast) };
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
