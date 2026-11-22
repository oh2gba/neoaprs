// Find my radio: asks the daemon (`find_radio`) to try the ports and speeds. The daemon reports
// each try (`radio_search`, state `trying`) and the end: `found`, `cancelled`, or an `error` with
// a code. The page shows one toast with Cancel while it runs. A found radio goes into the
// settings like any other change, or a notice says the settings have it already. The search
// ends for the page when the socket closes. It is for one radio: the box the button is in
// (`start` with its id, or the element's `data-radio`, `data-radio-name` and `data-radio-type`),
// else radio 1. One search runs at a time, so every box's button waits meanwhile.
import { computed, ref, shallowRef, watch, type Ref } from "vue";
import type { Toast } from "@/composables/useDaemon";
import type { Settings } from "@/composables/useSettings";
import { t } from "@/i18n";
import type { Connection } from "@/lib/hub";
import type { RadioId } from "@/lib/radios";
import type { Command, ConfigValues, RadioSearchMessage } from "@/protocol/protocol";

interface Target {
  id: RadioId | null;
  name: string;
  type: string;
}
const NONE: Target = { id: null, name: "", type: "" };
const FIRST: RadioId = 1;

function targetOf(given: RadioId | Event | undefined): Target {
  if (typeof given === "number") return { ...NONE, id: given };
  const box = given?.currentTarget instanceof Element ? given.currentTarget.closest<HTMLElement>("[data-radio]") : null;
  const id = Number(box?.dataset["radio"] ?? "");
  return Number.isInteger(id) && id > 0
    ? { id, name: box?.dataset["radioName"] ?? "", type: box?.dataset["radioType"] ?? "" }
    : NONE;
}

function foundOwn(found: RadioSearchMessage, id: RadioId): Record<string, string> {
  const values: Record<string, string> = { [`radio/${id}/port`]: found.port };
  if (found.baud !== null) values[`radio/${id}/baud`] = String(found.baud);
  return values;
}

export function useFindRadio(
  radioSearch: Ref<RadioSearchMessage | null>,
  lastError: Ref<Toast | null>,
  connection: Ref<Connection>,
  send: (command: Command) => boolean,
  settings: Pick<Settings, "change" | "expected">,
  config: Ref<ConfigValues | null>,
  say: (text: string) => void,
) {
  const running = ref(false);
  const target = shallowRef<Target>(NONE);
  const step = shallowRef<RadioSearchMessage | null>(null);
  const text = computed(() => {
    const now = step.value;
    const values = now === null ? null : { port: now.port, baud: now.baud ?? 0, number: now.number, total: now.total };
    const line =
      now === null || values === null
        ? t("settings.find.searching")
        : now.baud === null
          ? t("settings.find.trying_port", values)
          : t("settings.find.trying", values);
    return target.value.name === "" ? line : t("radio.line", { name: target.value.name, line });
  });

  function end(): void {
    running.value = false;
    step.value = null;
  }

  function found(message: RadioSearchMessage): void {
    const id = target.value.id ?? FIRST;
    const type = message.radio_type;
    if (type !== "" && type !== target.value.type) send({ cmd: "radio_change", radio: id, type });
    put(foundOwn(message, id), message.port);
  }

  /** Put what was found into the settings where it differs, else say they have it already. */
  function put(wanted: Record<string, string>, port: string): void {
    const changes = Object.fromEntries(
      Object.entries(wanted).filter(([key, value]) => settings.expected(key) !== value),
    );
    if (Object.keys(changes).length > 0) settings.change(changes);
    else say(t("settings.find.already", { port }));
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
  // A failed search ends with the daemon's error, which the error toast shows.
  watch(lastError, (toast) => {
    if (toast !== null && running.value && toast.cmd === "find_radio") end();
  });
  watch(connection, (state) => {
    if (state !== "open") end();
  });

  /** Start the search for the radio of the box, radio 1 if it names none. */
  function start(radio?: RadioId | Event): void {
    if (running.value || config.value === null) return;
    step.value = null;
    target.value = targetOf(radio);
    const id = target.value.id;
    running.value = send(id === null ? { cmd: "find_radio" } : { cmd: "find_radio", radio: id });
  }

  function cancel(): void {
    const id = target.value.id;
    if (running.value) send(id === null ? { cmd: "find_radio_cancel" } : { cmd: "find_radio_cancel", radio: id });
  }

  return { running, text, start, cancel };
}

export type FindRadio = ReturnType<typeof useFindRadio>;
