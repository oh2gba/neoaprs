// The first-run guide's state (components/SetupGuide.vue): whether it is open, the step, the answers (useSetupAnswers) and Finish. It lives as long as the page does, so that closing the guide and opening it again finds the answers where they
// were. Finish, on the Radio step, sends one `set_config` with the keys the answers change. An error of the daemon that names a key is shown under its field, and the guide goes to the step that has it. The place of the Position step is sent
// when the guide goes on from it, else the daemon is told the map is wanted: it makes the map round the place at once, without a click, unless the one it has covers the place (neoaprs/services/mapauto.py), so that it is
// there soon after the guide. The Radio step is live, as the Radio group of the Settings tab is (components/SetupRadio.vue): its radios are saved as they are changed and stay when the guide is closed, and what it needs before
// Finish is the page's radios' (lib/setup.ts `radioReady`), not answers; the ports and sound cards are asked for again each time it comes on the screen, so that a radio plugged in meanwhile is listed.
import { computed, reactive, ref, watch, type Ref } from "vue";
import { useSetupAnswers } from "@/composables/useSetupAnswers";
import { useSetupSave } from "@/composables/useSetupSave";
import type { Toast } from "@/composables/useDaemon";
import { LAST_STEP, RADIO_STEP } from "@/lib/setup";
import type { Command, ConfigValues } from "@/protocol/protocol";

export function useSetupGuide(config: Ref<ConfigValues | null>, lastError: Ref<Toast | null>, send: (command: Command) => boolean) {
  const open = ref(false);
  const step = ref(0);
  const peeking = ref(false); // only the head shows, so that the map can be clicked on a narrow page
  const reached = ref(0); // the furthest step the user has been on: the steps up to it that are right show as done
  const values = computed(() => config.value?.values ?? {});
  const answers = useSetupAnswers(values);
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
  const { saving, finish } = useSetupSave(answers, config, lastError, send, step, done);

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

  /** Next, or Finish on the last step. */
  function next(): void {
    if (!valid.value[step.value]) return;
    if (step.value >= LAST_STEP) finish();
    else step.value += 1;
  }

  watch(onRadio, (shown) => shown && send({ cmd: "list_ports" }));

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
    /** Only the head shows (on) or all of it (off). */
    peek: (on: boolean) => (peeking.value = on),
    place,
    go,
    back: () => go(step.value - 1),
    next,
    finish,
  });
}

export type SetupGuide = ReturnType<typeof useSetupGuide>;
