// The first-run guide's state (components/SetupGuide.vue): whether it is open, the step, the answers (useSetupAnswers) and Finish. It lives as long as the page does, so that closing the guide and opening it again finds the answers where they
// were. Finish sends one `set_config` with the keys the answers change; the Map step's Estimate and Download send it first when there is something to save (the daemon makes the map for the settings it has), and the command follows when the
// daemon has told the settings again. An error of the daemon that names a key is shown under its field, and the guide goes to the step that has it.
import { computed, reactive, ref, watch, type Ref } from "vue";
import { useSetupAnswers } from "@/composables/useSetupAnswers";
import { useSetupSave } from "@/composables/useSetupSave";
import type { Toast } from "@/composables/useDaemon";
import { LAST_STEP } from "@/lib/setup";
import type { Command, ConfigValues, PortsMessage } from "@/protocol/protocol";

export function useSetupGuide(
  config: Ref<ConfigValues | null>,
  lastError: Ref<Toast | null>,
  ports: Ref<PortsMessage | null>,
  send: (command: Command) => boolean,
) {
  const open = ref(false);
  const step = ref(0);
  const peeking = ref(false); // only the head shows, so that the map can be clicked on a narrow page
  const reached = ref(0); // the furthest step the user has been on: the steps up to it that are right show as done

  const values = computed(() => config.value?.values ?? {});
  const search = computed(() => ports.value?.search ?? null);
  const answers = useSetupAnswers(values, search);
  const { fields, changes, valid } = answers;
  const picking = computed(() => open.value && step.value === 1);

  /** The guide is finished: closed, and the answers are the settings again. */
  function done(): void {
    close();
    answers.reset();
    step.value = 0;
    reached.value = 0;
  }
  const { saving, finish, sendMap } = useSetupSave(answers, config, lastError, send, step, done);

  watch(step, (now) => (reached.value = Math.max(reached.value, now)));

  function show(): void {
    open.value = true;
  }

  function close(): void {
    open.value = false;
    peeking.value = false;
  }

  function refreshPorts(): void {
    send({ cmd: "list_ports" });
  }

  function place(lat: number, lon: number): void {
    answers.place(lat, lon);
    peeking.value = false;
  }

  function go(to: number): void {
    if (to >= 0 && to <= LAST_STEP && (to <= step.value || valid.value.slice(0, to).every(Boolean))) step.value = to;
  }

  /** Next, or Finish on the last step. */
  function next(): void {
    if (!valid.value[step.value]) return;
    if (step.value >= LAST_STEP) finish();
    else step.value += 1;
  }

  watch(
    () => open.value && step.value === 3 && !answers.tcp.value,
    (wanted) => {
      if (wanted) refreshPorts();
    },
  );

  return reactive({
    open,
    step,
    peeking,
    reached,
    saving,
    picking,
    search,
    ports: computed(() => ports.value),
    fields,
    problems: answers.problems,
    valid,
    changes,
    pin: answers.pin,
    tcp: answers.tcp,
    edit: answers.edit,
    show,
    close,
    /** Only the head shows (on) or all of it (off). */
    peek: (on: boolean) => (peeking.value = on),
    place,
    go,
    back: () => go(step.value - 1),
    next,
    finish,
    sendMap,
    refreshPorts,
  });
}

export type SetupGuide = ReturnType<typeof useSetupGuide>;
