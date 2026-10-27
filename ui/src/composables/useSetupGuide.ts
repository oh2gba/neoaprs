// The first-run guide's state (components/SetupGuide.vue): whether it is open, the step, the answers (useSetupAnswers) and Finish. It lives as long as the page does, so that closing the guide and opening it again finds the answers where they
// were. Finish sends one `set_config` with the keys the answers change; the Map step's Estimate and Download send it first when there is something to save (the daemon makes the map for the settings it has), and the command follows when the
// daemon has told the settings again. An error of the daemon that names a key is shown under its field, and the guide goes to the step that has it. The place of the Position step is sent when the guide goes on from it, while the daemon has no detailed
// map: the daemon makes the map round it at once, without a click (neoaprs/services/mapauto.py), so that it is there when the guide ends.
import { computed, reactive, ref, watch, type Ref } from "vue";
import { useSetupAnswers } from "@/composables/useSetupAnswers";
import { useSetupSave } from "@/composables/useSetupSave";
import type { Toast } from "@/composables/useDaemon";
import { LAST_STEP, RADIO_STEP } from "@/lib/setup";
import type { Command, ConfigValues, MapState, PortsMessage } from "@/protocol/protocol";

export function useSetupGuide(
  config: Ref<ConfigValues | null>,
  lastError: Ref<Toast | null>,
  ports: Ref<PortsMessage | null>,
  send: (command: Command) => boolean,
  map: Ref<MapState | null> = ref(null),
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
  const onRadio = computed(() => open.value && step.value === RADIO_STEP); // the Radio step is on the screen

  /** The guide is finished: closed, and the answers are the settings again. */
  function done(): void {
    close();
    answers.reset();
    step.value = 0;
    reached.value = 0;
  }
  const { saving, finish, applyRadio } = useSetupSave(answers, config, lastError, send, step, done, map);

  watch(step, (now) => (reached.value = Math.max(reached.value, now)));

  function show(): void {
    open.value = true;
  }

  function close(): void {
    open.value = false;
    peeking.value = false;
  }

  const refreshPorts = (): void => void send({ cmd: "list_ports" });

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
    () => onRadio.value && !answers.tcp.value && !answers.dummy.value, // (only a serial TNC has a port to pick)
    (wanted) => wanted && refreshPorts(),
  );

  return reactive({
    open,
    step,
    peeking,
    reached,
    saving,
    picking,
    onRadio,
    search,
    ports: computed(() => ports.value),
    fields,
    problems: answers.problems,
    valid,
    changes,
    pin: answers.pin,
    tcp: answers.tcp,
    fillRadio: answers.fillRadio,
    applyRadio,
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
    refreshPorts,
  });
}

export type SetupGuide = ReturnType<typeof useSetupGuide>;
