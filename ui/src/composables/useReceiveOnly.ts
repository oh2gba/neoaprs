// Whether transmitting is switched off (`station/transmit` false, "RX only"): the buttons that send are off then, with the title "RX only: nothing is sent". Read from the page's context; a pane mounted without one (a test) is not RX only.
import { computed, inject, type Ref } from "vue";
import { DAEMON_KEY } from "@/composables/useDaemonContext";

export function useReceiveOnly(): Readonly<Ref<boolean>> {
  const context = inject(DAEMON_KEY, null);
  return computed(() => context?.receiveOnly.value ?? false);
}
