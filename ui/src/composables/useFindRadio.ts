// Find my radio: the button of the Settings tab asks the daemon (`find_radio`) to try the ports and the speeds, and the daemon tells each try (`radio_search`, state `trying`) and the end of it: `found`, `cancelled`, or an `error` with a
// code (nothing answered, no port to try). The page shows it in one toast (FindRadioToast) while it runs, with Cancel. A radio that was found goes into the settings like any other change (the Undo toast follows it), or is said in a
// notice when the settings have it already, also from the setup guide's Radio step, which is live as the Settings tab is (plan section 6). The search ends for the page when the socket closes: the daemon ends it when its page has gone.
// The search is for one radio: the one whose box the button is in (`start` with its id, or with the click of a button inside the box, whose element says the radio: `data-radio`, and its name where several radios are named,
// `data-radio-name`, and its type, `data-radio-type`), else radio 1, the FM radio of before, as the command without a radio means. One search runs at a time, so every box's button waits while one does; the toast names the radio where several are named, and
// what is found goes into that radio's own settings (`radio/<id>/port`, its type by `radio_change`), radio 1's into the settings of before.
import { computed, ref, shallowRef, watch, type Ref } from "vue";
import type { Toast } from "@/composables/useDaemon";
import type { Settings } from "@/composables/useSettings";
import { t } from "@/i18n";
import type { Connection } from "@/lib/hub";
import { FM_ID } from "@/lib/radiosides";
import type { RadioId } from "@/lib/radios";
import type { Command, ConfigValues, RadioSearchMessage } from "@/protocol/protocol";

/** The radio a search is for, its name where the toast names it (empty where one radio is on) and its type (empty where the box does not say). */
interface Target {
  id: RadioId | null;
  name: string;
  type: string;
}
const NONE: Target = { id: null, name: "", type: "" };

/** The radio of the box a press came from: the id the caller gives, else the one its element says (the box's `data-radio`, with `data-radio-name`); none for a press outside a radio's box. */
function targetOf(given: RadioId | Event | undefined): Target {
  if (typeof given === "number") return { ...NONE, id: given };
  const box = given?.currentTarget instanceof Element ? given.currentTarget.closest<HTMLElement>("[data-radio]") : null;
  const id = Number(box?.dataset["radio"] ?? "");
  return Number.isInteger(id) && id > 0 ? { id, name: box?.dataset["radioName"] ?? "", type: box?.dataset["radioType"] ?? "" } : NONE;
}

/** What a found radio makes of the settings of a radio other than radio 1: its own port and, for a port that has a speed, its own speed. */
function foundOwn(found: RadioSearchMessage, id: RadioId): Record<string, string> {
  const values: Record<string, string> = { [`radio/${id}/port`]: found.port };
  if (found.baud !== null) values[`radio/${id}/baud`] = String(found.baud);
  return values;
}

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
  settings: Pick<Settings, "change" | "expected">,
  config: Ref<ConfigValues | null>,
  say: (text: string) => void,
  _guide?: unknown, // (the guide of before, whose Radio step had answers of its own; useAppShell.ts still passes it)
) {
  const running = ref(false);
  /** The radio the search is for. */
  const target = shallowRef<Target>(NONE);
  /** The try that is under way; null until the daemon has told the first. */
  const step = shallowRef<RadioSearchMessage | null>(null);
  /** The words of the toast while it runs, after the radio's name where several radios are named. */
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
    const id = target.value.id;
    if (id === null || id === FM_ID) return put(foundSettings(message), message.port);
    const type = message.radio_type || message.profile; // (a radio other than radio 1: its type, when the TNC found is of another, then its own port and speed)
    if (type !== "" && type !== target.value.type) send({ cmd: "radio_change", radio: id, type });
    put(foundOwn(message, id), message.port);
  }

  /** What was found goes into the settings where it differs, else the notice says the settings have it already. */
  function put(wanted: Record<string, string>, port: string): void {
    const changes = Object.fromEntries(Object.entries(wanted).filter(([key, value]) => settings.expected(key) !== value));
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
  // a search that fails (nothing answered, no port to try) ends with the daemon's error, which the toast of errors shows
  watch(lastError, (toast) => {
    if (toast !== null && running.value && toast.cmd === "find_radio") end();
  });
  watch(connection, (state) => {
    if (state !== "open") end();
  });

  /** Starts the search for the radio of the box (its id, or the press of a button inside its box), radio 1 when it names none. */
  function start(radio?: RadioId | Event): void {
    if (running.value || config.value === null) return;
    step.value = null;
    target.value = targetOf(radio);
    const id = target.value.id;
    running.value = send(id === null || id === FM_ID ? { cmd: "find_radio" } : { cmd: "find_radio", radio: id });
  }

  function cancel(): void {
    const id = target.value.id;
    if (running.value) send(id === null || id === FM_ID ? { cmd: "find_radio_cancel" } : { cmd: "find_radio_cancel", radio: id });
  }

  return { running, text, start, cancel };
}

export type FindRadio = ReturnType<typeof useFindRadio>;
