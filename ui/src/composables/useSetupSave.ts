// How the first-run guide saves: Finish sends one `set_config` with the keys the answers change
// (call, place, symbol, a new station's beacon) and a number of its own (useSettingsQueue saveId);
// the radios of the Radio step are saved as changed. The answer is `saved` or an `error` with that
// number; a daemon error naming a key shows under its field and the guide goes to its step. An error
// of another command does not end the wait; a daemon that never answers does after ANSWER_MS. When
// the guide goes on from the Position step, the place is sent on its own if the answers changed it,
// else `map_wanted` says the map of the area is wanted (the daemon makes it unless its map covers
// the place).
import { computed, watch, type Ref } from "vue";
import type { useSetupAnswers } from "@/composables/useSetupAnswers";
import type { Toast } from "@/composables/useDaemon";
import { endWithTheSocket, useInFlight } from "@/composables/useInFlight";
import { saveId } from "@/composables/useSettingsQueue";
import type { Connection } from "@/lib/hub";
import { reasonOf } from "@/lib/settings";
import { KEY_OF, STEP_OF } from "@/lib/setup";
import type { Command, ConfigValues, SavedMessage } from "@/protocol/protocol";

export function useSetupSave(
  answers: ReturnType<typeof useSetupAnswers>,
  config: Ref<ConfigValues | null>,
  lastError: Ref<Toast | null>,
  send: (command: Command) => boolean,
  step: Ref<number>,
  done: () => void,
  connection?: Readonly<Ref<Connection>>,
  saved?: Readonly<Ref<SavedMessage | null>>,
) {
  const flight = useInFlight("set_config", null, null);
  const saving = flight.busy;
  endWithTheSocket(connection, flight.land);
  /** The number of Finish's save while it is out. */
  let out = 0;
  const nothing = computed(() => Object.keys(answers.changes.value).length === 0);

  function save(): void {
    answers.clearErrors();
    out = saveId();
    flight.run(() => send({ cmd: "set_config", values: { ...answers.changes.value }, id: out }));
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
    const values = Object.fromEntries(
      Object.entries(answers.changes.value).filter(([key]) => key === "station/lat" || key === "station/lon"),
    );
    send(Object.keys(values).length > 0 ? { cmd: "set_config", values } : { cmd: "map_wanted" });
  });

  watch(
    config,
    (now) => {
      if (now && !saving.value && !answers.touched.value) answers.fill(now.values);
    },
    { immediate: true },
  );

  if (saved)
    watch(saved, (message) => {
      if (!message || !saving.value || message.id !== out) return;
      flight.land();
      done();
    });

  // The refusal of Finish's save: an error with its number, or one without a number that names a
  // key Finish sends (another key is a radio's, shown under that field there).
  watch(lastError, (toast) => {
    if (!toast || !saving.value || toast.cmd !== "set_config") return;
    if (toast.id != null && toast.id !== out) return;
    const named = toast.cmd === "set_config" && toast.key !== null;
    const field = named && toast.key !== null ? KEY_OF[toast.key] : undefined;
    if (named && !field && toast.id == null) return;
    flight.land();
    if (!field) return;
    answers.errors[field] = reasonOf(toast);
    step.value = STEP_OF[field];
  });

  return { saving, finish };
}
