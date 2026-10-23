// The station the user picked: a marker on the map only selects it, a row of the table selects it and flies the map to it (`focus`, which counts up so that the same station picked twice flies twice).
// A station the daemon no longer has (forgotten, pruned) is let go of.
import { computed, ref, watch, type Ref } from "vue";
import type { Focus } from "@/lib/mapview";
import type { Command, StationRow } from "@/protocol/protocol";

export function useSelection(stations: Readonly<Ref<ReadonlyMap<string, StationRow>>>, send: (command: Command) => boolean) {
  const selected = ref<string | null>(null);
  const focus = ref<Focus | null>(null);
  let asked = 0;
  const row = computed(() => (selected.value === null ? null : (stations.value.get(selected.value) ?? null)));
  watch(row, (now) => {
    if (now === null) selected.value = null;
  });

  /** A station picked in the table: selected, and the map flies to it. */
  function pickFromTable(call: string): void {
    selected.value = call;
    focus.value = { call, n: ++asked };
  }

  /** The Forget of a station's card: the daemon forgets it, and it is no longer selected. */
  function forget(call: string): void {
    if (send({ cmd: "forget_station", call })) selected.value = null;
  }

  return { selected, focus, row, pickFromTable, forget };
}
