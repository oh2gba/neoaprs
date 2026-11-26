// Do something again when the socket to the daemon opens after it was not open: what a page asked
// once is answered once, and the daemon forgets a gone page's asks.
import { watch, type Ref } from "vue";
import type { Connection } from "@/lib/hub";

export function onReopen(connection: Readonly<Ref<Connection>>, again: () => void): void {
  watch(connection, (state, before) => {
    if (state === "open" && before !== "open") again();
  });
}
