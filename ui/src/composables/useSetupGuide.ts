// The first-run guide's state: whether it is open, the step, the answers (useSetupAnswers) and
// Finish. It lives as long as the page, so reopening finds the answers. Finish, on the Radio
// step, sends one `set_config` with the keys the answers change. A daemon error naming a key is
// shown under its field and the guide goes to its step. The Position step's place is sent when
// the guide goes on from it, else the daemon is told the map is wanted
// (neoaprs/services/mapauto.py).
// The Radio step is live as the Radio group of Settings is: its radios are saved as changed and
// stay when the guide closes; what Finish needs from it is `radioReady` (lib/setup.ts). The ports
// and sound cards are asked again each time it shows, so a radio plugged in meanwhile is listed.
import { computed, reactive, ref, watch, type Ref } from "vue";
import { useSetupAnswers } from "@/composables/useSetupAnswers";
import { useSetupSave } from "@/composables/useSetupSave";
import type { Toast } from "@/composables/useDaemon";
import type { Connection } from "@/lib/hub";
import { LAST_STEP, RADIO_STEP } from "@/lib/setup";
import { portsAsks } from "@/lib/radios";
import type { Command, ConfigValues, RadioRow, SavedMessage } from "@/protocol/protocol";

export function useSetupGuide(
  config: Ref<ConfigValues | null>,
  lastError: Ref<Toast | null>,
  send: (command: Command) => boolean,
  radios: Readonly<Ref<ReadonlyMap<string, RadioRow> | null>> | null = null,
  connection?: Readonly<Ref<Connection>>,
  saved?: Readonly<Ref<SavedMessage | null>>,
) {
  const open = ref(false);
  const step = ref(0);
  // Only the head shows, so that the map can be clicked on a narrow page.
  const peeking = ref(false);
  // The furthest step reached: the right steps up to it show as done.
  const reached = ref(0);
  const values = computed(() => config.value?.values ?? {});
  const answers = useSetupAnswers(values);
  const { fields, changes, valid } = answers;
  const picking = computed(() => open.value && step.value === 1);
  const onRadio = computed(() => open.value && step.value === RADIO_STEP);

  function done(): void {
    close();
    answers.reset();
    step.value = 0;
    reached.value = 0;
  }
  const { saving, finish } = useSetupSave(answers, config, lastError, send, step, done, connection, saved);

  watch(step, (now) => (reached.value = Math.max(reached.value, now)));

  function show(): void {
    open.value = true;
  }

  function close(): void {
    open.value = false;
    peeking.value = false;
  }

  function place(lat: number, lon: number): void {
    answers.place(lat, lon);
    peeking.value = false;
  }

  function go(to: number): void {
    if (to >= 0 && to <= LAST_STEP && (to <= step.value || valid.value.slice(0, to).every(Boolean))) step.value = to;
  }

  function next(): void {
    if (!valid.value[step.value]) return;
    if (step.value >= LAST_STEP) finish();
    else step.value += 1;
  }

  watch(onRadio, (shown) => {
    if (shown) for (const ask of portsAsks(radios?.value?.values() ?? [])) send(ask);
  });

  return reactive({
    open,
    step,
    peeking,
    reached,
    saving,
    picking,
    onRadio,
    fields,
    problems: answers.problems,
    valid,
    changes,
    pin: answers.pin,
    edit: answers.edit,
    show,
    close,
    peek: (on: boolean) => (peeking.value = on),
    place,
    go,
    back: () => go(step.value - 1),
    next,
    finish,
  });
}

export type SetupGuide = ReturnType<typeof useSetupGuide>;
