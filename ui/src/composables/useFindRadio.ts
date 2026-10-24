// Find my radio: the button of the Settings tab asks the daemon (`find_radio`) to try the ports and the speeds, and the daemon tells each try (`radio_search`, state `trying`) and the end of it: `found`, `cancelled`, or an `error` with a
// code (nothing answered, no port to try). The page shows it in one toast (FindRadioToast) while it runs, with Cancel. A radio that was found goes into the settings like any other change (the Undo toast follows it), or is said in a
// notice when the settings have it already. The search ends for the page when the socket closes: the daemon ends it when its page has gone.
import { computed, ref, shallowRef, watch, type Ref } from "vue";
import type { Toast } from "@/composables/useDaemon";
import type { Settings } from "@/composables/useSettings";
import { t } from "@/i18n";
import type { Connection } from "@/lib/hub";
import type { Command, ConfigValues, RadioSearchMessage } from "@/protocol/protocol";

/** What a found radio makes of the settings: the port, the type of TNC and, for a port that has a speed, the speed. */
export function foundSettings(found: RadioSearchMessage): Record<string, string> {
  const values: Record<string, string> = { "tnc/profile": found.profile, "serial/port": found.port };
  if (found.baud !== null) values["serial/baud"] = String(found.baud);
  return values;
}

export function useFindRadio(
  radioSearch: Ref<RadioSearchMessage | null>,
  lastError: Ref<Toast | null>,
  connection: Ref<Connection>,
  send: (command: Command) => boolean,
  settings: Pick<Settings, "change" | "expected" | "dismissUndo">,
  config: Ref<ConfigValues | null>,
  say: (text: string) => void,
) {
  const running = ref(false);
  /** The try that is under way; null until the daemon has told the first. */
  const step = shallowRef<RadioSearchMessage | null>(null);
  /** The words of the toast while it runs. */
  const text = computed(() => {
    const now = step.value;
    if (now === null) return t("settings.find.searching");
    const values = { port: now.port, baud: now.baud ?? 0, number: now.number, total: now.total };
    return now.baud === null ? t("settings.find.trying_port", values) : t("settings.find.trying", values);
  });

  function end(): void {
    running.value = false;
    step.value = null;
  }

  function found(message: RadioSearchMessage): void {
    const wanted = foundSettings(message);
    const changes = Object.fromEntries(Object.entries(wanted).filter(([key, value]) => settings.expected(key) !== value));
    if (Object.keys(changes).length > 0) settings.change(changes);
    else say(t("settings.find.already", { port: message.port }));
  }

  watch(radioSearch, (message) => {
    if (message === null || !running.value) return;
    if (message.state === "trying") {
      step.value = message;
      return;
    }
    end();
    if (message.state === "found") found(message);
    else say(t("settings.find.cancelled"));
  });
  // a search that fails (nothing answered, no port to try) ends with the daemon's error, which the toast of errors shows
  watch(lastError, (toast) => {
    if (toast !== null && running.value && toast.cmd === "find_radio") end();
  });
  watch(connection, (state) => {
    if (state !== "open") end();
  });

  function start(): void {
    if (running.value || config.value === null) return;
    step.value = null;
    settings.dismissUndo(); // (the toast of the search takes its place)
    running.value = send({ cmd: "find_radio" });
  }

  function cancel(): void {
    if (running.value) send({ cmd: "find_radio_cancel" });
  }

  return { running, text, start, cancel };
}

export type FindRadio = ReturnType<typeof useFindRadio>;
