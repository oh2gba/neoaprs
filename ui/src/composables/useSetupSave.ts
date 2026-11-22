// How the first-run guide saves: Finish sends one `set_config` with the keys the answers change
// (call, place, symbol, a new station's beacon); the radios of the Radio step are saved as
// changed, and the topic `config` after a save is the answer. A daemon error naming a key shows
// under its field and the guide goes to its step. When the guide goes on from the Position step,
// the place is sent on its own if the answers changed it, else `map_wanted` says the map of the
// area is wanted (the daemon makes it unless its map covers the place).
import { computed, ref, watch, type Ref } from "vue";
import type { useSetupAnswers } from "@/composables/useSetupAnswers";
import type { Toast } from "@/composables/useDaemon";
import { endWithTheSocket } from "@/composables/useInFlight";
import type { Connection } from "@/lib/hub";
import { reasonOf } from "@/lib/settings";
import { KEY_OF, STEP_OF } from "@/lib/setup";
import type { Command, ConfigValues } from "@/protocol/protocol";

export function useSetupSave(
  answers: ReturnType<typeof useSetupAnswers>,
  config: Ref<ConfigValues | null>,
  lastError: Ref<Toast | null>,
  send: (command: Command) => boolean,
  step: Ref<number>,
  done: () => void,
  connection?: Readonly<Ref<Connection>>,
) {
  const saving = ref(false);
  endWithTheSocket(connection, () => (saving.value = false));
  /**
   * What the daemon held of each key the save names when Finish sent it: a config with none of them
   * changed answers another save.
   */
  let held: Record<string, string> = {};
  const nothing = computed(() => Object.keys(answers.changes.value).length === 0);

  function save(): void {
    answers.clearErrors();
    const values = { ...answers.changes.value };
    const before = config.value?.values ?? {};
    held = Object.fromEntries(Object.keys(values).map((key) => [key, before[key] ?? ""]));
    saving.value = send({ cmd: "set_config", values });
  }

  /**
   * Finish: show the first step that is not right, else save the changed keys (nothing if none
   * changed).
   */
  function finish(): void {
    const bad = answers.valid.value.findIndex((ok) => !ok);
    if (bad >= 0) step.value = bad;
    else if (saving.value) return;
    else if (nothing.value) done();
    else save();
  }

  /**
   * Going on from the Position step: save the place alone if the answers changed it, else say the
   * map of the area is wanted. One command, not two: the daemon runs commands side by side, so
   * the second could not count on the save.
   */
  watch(step, (now, before) => {
    if (before !== STEP_OF.lat || now <= before) return;
    const values = Object.fromEntries(Object.entries(answers.changes.value).filter(([key]) => key === "station/lat" || key === "station/lon"));
    send(Object.keys(values).length > 0 ? { cmd: "set_config", values } : { cmd: "map_wanted" });
  });

  watch(
    config,
    (now) => {
      if (!now) return;
      if (!saving.value) {
        if (!answers.touched.value) answers.fill(now.values);
        return;
      }
      if (Object.entries(held).every(([key, text]) => (now.values[key] ?? "") === text)) return;
      saving.value = false;
      done();
    },
    { immediate: true },
  );

  // The refusal of Finish's save; one naming a key Finish does not send is a radio's, shown under
  // that field there.
  watch(lastError, (toast) => {
    if (!toast || !saving.value) return;
    const named = toast.cmd === "set_config" && toast.key !== null;
    const field = named && toast.key !== null ? KEY_OF[toast.key] : undefined;
    if (named && !field) return;
    saving.value = false;
    if (!field) return;
    answers.errors[field] = reasonOf(toast);
    step.value = STEP_OF[field];
  });

  return { saving, finish };
}
