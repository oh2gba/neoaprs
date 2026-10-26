// How the first-run guide saves (composables/useSetupGuide.ts): Finish sends one `set_config` with the keys the answers change; Estimate and Download of the Map step send it first when there is something to save, and their command goes out when the
// daemon has told the settings again (the topic `config` told after a save is the answer). The daemon's error that names a key is shown under its field, and the guide goes to the step that has it.
import { computed, ref, watch, type Ref } from "vue";
import type { useSetupAnswers } from "@/composables/useSetupAnswers";
import type { Toast } from "@/composables/useDaemon";
import { reasonOf } from "@/lib/settings";
import { KEY_OF, radioChanges, STEP_OF } from "@/lib/setup";
import type { Command, ConfigValues } from "@/protocol/protocol";

export function useSetupSave(
  answers: ReturnType<typeof useSetupAnswers>,
  config: Ref<ConfigValues | null>,
  lastError: Ref<Toast | null>,
  send: (command: Command) => boolean,
  step: Ref<number>,
  done: () => void,
) {
  const saving = ref(false);
  let finishing = false;
  let pending: Command | null = null; // the map command that waits for the settings to be saved
  const nothing = computed(() => Object.keys(answers.changes.value).length === 0);

  function save(final: boolean, values: Record<string, string> = answers.changes.value): boolean {
    answers.clearErrors();
    finishing = final;
    saving.value = send({ cmd: "set_config", values: { ...values } });
    return saving.value;
  }

  /** The Terminal of the Radio step: the radio the answers name is put in force (the settings of the radio only), so that the terminal shows that radio; nothing is sent when it is the one in force. */
  function applyRadio(): void {
    const radio = radioChanges(answers.fields, config.value?.values ?? {});
    if (Object.keys(radio).length > 0 && !saving.value) save(false, radio);
  }

  /** Finish: the first step that is not right is shown, else the changed keys are saved, or nothing is when none is changed. */
  function finish(): void {
    const bad = answers.valid.value.findIndex((ok) => !ok);
    if (bad >= 0) step.value = bad;
    else if (saving.value) return;
    else if (nothing.value) done();
    else save(true);
  }

  /** The Map step's commands: the settings are saved first when the answers differ from them, the map command follows. */
  function sendMap(command: Command): boolean {
    if ((command.cmd !== "map_estimate" && command.cmd !== "map_fetch") || nothing.value) return send(command);
    if (saving.value) return false;
    pending = command;
    return save(false);
  }

  watch(
    config,
    (now) => {
      if (!now) return;
      if (!saving.value) {
        if (!answers.touched.value) answers.fill(now.values); // (the daemon's word is the answer until the user answers)
        return;
      }
      saving.value = false;
      if (finishing) {
        finishing = false;
        done();
      } else if (pending) {
        const command = pending;
        pending = null;
        send(command);
      }
    },
    { immediate: true },
  );

  watch(lastError, (toast) => {
    if (!toast || !saving.value) return;
    saving.value = false;
    finishing = false;
    pending = null;
    const field = toast.cmd === "set_config" && toast.key !== null ? KEY_OF[toast.key] : undefined;
    if (!field) return;
    answers.errors[field] = reasonOf(toast);
    step.value = STEP_OF[field];
  });

  return { saving, finish, sendMap, applyRadio };
}
