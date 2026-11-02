// What the panes ask of the radios that are on, read from the page's settings (lib/radiosides.ts). A pane mounted without the page's context (a test of its own) is as a station with the FM radio alone.
import { computed, inject, type ComputedRef } from "vue";
import { DAEMON_KEY } from "@/composables/useDaemonContext";
import { fmOn, hfOn } from "@/lib/radiosides";

/** Whether the radios are named on the page: only where there are two, that is while the HF radio is on, the FM radio's tag is "FM" beside "HF"; else "RF" as it always was. */
export function useRadiosNamed(): ComputedRef<boolean> {
  const context = inject(DAEMON_KEY, null);
  return computed(() => context?.radiosNamed.value ?? false);
}

/** Whether both radios are on: the one case where a choice of the radio (the Radio row of an object, its tag in the list) means anything. */
export function useTwoRadios(): ComputedRef<boolean> {
  const context = inject(DAEMON_KEY, null);
  return computed(() => {
    const values = context?.config.value?.values ?? {};
    return context !== null && fmOn(values) && hfOn(values);
  });
}

/** Whether the FM radio is off: what goes out over it alone (the email gateway, which needs an iGate on the air) cannot be sent. */
export function useFmOff(): ComputedRef<boolean> {
  const context = inject(DAEMON_KEY, null);
  return computed(() => context !== null && !fmOn(context.config.value?.values ?? {}));
}
