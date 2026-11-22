// Page errors go to the daemon through the socket, quietly, waiting while it is closed: a toast for
// an unreportable error would be one more error.
import { onBeforeUnmount, onMounted, watch, type Ref } from "vue";
import type { Connection, Hub } from "@/lib/hub";
import { pageErrors } from "@/lib/pageerrors";

export function usePageErrorReport(hub: Pick<Hub, "send">, connection: Readonly<Ref<Connection>>): void {
  watch(connection, (state) => state === "open" && pageErrors.flush(), { flush: "sync" });
  onMounted(() => pageErrors.attach((command) => hub.send(command)));
  onBeforeUnmount(() => pageErrors.detach());
}
