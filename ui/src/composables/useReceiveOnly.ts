// Whether transmitting is off (`station/transmit` false, "RX only"). Read from the page's context;
// a pane mounted without one is not RX only.
import { computed, inject, type Ref } from "vue";
import { DAEMON_KEY } from "@/composables/useDaemonContext";

export function useReceiveOnly(): Readonly<Ref<boolean>> {
  const context = inject(DAEMON_KEY, null);
  return computed(() => context?.receiveOnly.value ?? false);
}
