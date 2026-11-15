// What the panes of today ask of the two radios of before (radio 1 the FM radio, radio 2 the HF radio): a view over composables/useRadios.ts. A pane mounted without the page's context (a test of its own) is as a station
// with the FM radio alone.
import { computed, inject, type ComputedRef } from "vue";
import { DAEMON_KEY } from "@/composables/useDaemonContext";
import { useRadios } from "@/composables/useRadios";
import { isOn } from "@/lib/radios";
import { FM_ID, HF_ID } from "@/lib/radiosides";

/** Whether the radios are named on the page: more than one radio is on (plan section 6). */
export function useRadiosNamed(): ComputedRef<boolean> {
  const context = inject(DAEMON_KEY, null);
  return computed(() => context?.radiosNamed.value ?? false);
}

/** Whether both radios are on: the one case where a choice of the radio (the Radio row of an object, its tag in the list) means anything. */
export function useTwoRadios(): ComputedRef<boolean> {
  const context = inject(DAEMON_KEY, null);
  const { all } = useRadios();
  return computed(() => context !== null && isOn(all.value, FM_ID) && isOn(all.value, HF_ID));
}

/** Whether the FM radio is off: what goes out over it alone (the email gateway, which needs an iGate on the air) cannot be sent. */
export function useFmOff(): ComputedRef<boolean> {
  const context = inject(DAEMON_KEY, null);
  const { all } = useRadios();
  return computed(() => context !== null && !isOn(all.value, FM_ID));
}
