// The errors of the page (lib/pageerrors.ts) go to the daemon through the page's socket, quietly: a toast for an error that could not be reported would be one more error. They wait while the socket is not open and are sent when it is.
import { onBeforeUnmount, onMounted, watch, type Ref } from "vue";
import type { Connection, Hub } from "@/lib/hub";
import { pageErrors } from "@/lib/pageerrors";

export function usePageErrorReport(hub: Pick<Hub, "send">, connection: Readonly<Ref<Connection>>): void {
  watch(connection, (state) => state === "open" && pageErrors.flush(), { flush: "sync" });
  onMounted(() => pageErrors.attach((command) => hub.send(command)));
  onBeforeUnmount(() => pageErrors.detach());
}
