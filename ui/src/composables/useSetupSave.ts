// How the first-run guide saves (composables/useSetupGuide.ts): Finish sends one `set_config` with the keys the answers change (the call, the place, the symbol and a new station's beacon: the radios of the Radio step were saved
// as they were changed, as in the Settings tab; the topic `config` told after a save is the answer). The daemon's error that names a key is shown under its field, and the guide
// goes to the step that has it. When the guide goes on from the Position step, the place is sent on its own when the answers change it (the daemon makes the map round a new place at once), else `map_wanted` says the map of the area is wanted
// (the daemon makes it unless the one it has covers the place); the guide says so in a quiet line, and the header shows the percent.
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
  /** What the daemon held, when Finish sent its save, of each key the save names: a config that holds none of them changed is the answer to another save (a radio's, sent from a box of the Radio step just before). */
  let held: Record<string, string> = {};
  const nothing = computed(() => Object.keys(answers.changes.value).length === 0);

  function save(): void {
    answers.clearErrors();
    const values = { ...answers.changes.value };
    const before = config.value?.values ?? {};
    held = Object.fromEntries(Object.keys(values).map((key) => [key, before[key] ?? ""]));
    saving.value = send({ cmd: "set_config", values });
  }

  /** Finish: the first step that is not right is shown, else the changed keys are saved, or nothing is when none is changed. */
  function finish(): void {
    const bad = answers.valid.value.findIndex((ok) => !ok);
    if (bad >= 0) step.value = bad;
    else if (saving.value) return;
    else if (nothing.value) done();
    else save();
  }

  /** Going on from the Position step: its place is saved on its own when the answers change it (the daemon makes the map round a new place), else the daemon is told the map of the area is wanted (it makes it unless
   * the one it has covers the place). One command, not two: the daemon runs commands side by side, so the second could not count on the save. */
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
        if (!answers.touched.value) answers.fill(now.values); // (the daemon's word is the answer until the user answers)
        return;
      }
      if (Object.entries(held).every(([key, text]) => (now.values[key] ?? "") === text)) return; // (not Finish's answer)
      saving.value = false;
      done();
    },
    { immediate: true },
  );

  // the refusal of Finish's save; one that names a key Finish does not send is a radio's, saved by a box of the Radio step, and stands under that field there
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
