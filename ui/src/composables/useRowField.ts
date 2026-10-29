// The field under a row of the Stations table (StationRowDetail), as the Packets tab opens a packet under its row: which station it is open for, one at a time. A click on a row (or Enter on it) opens the field under that row,
// moving it from the row it was under, and the same again closes it; Up and Down, which select the next row, take an open field along. Esc in the field closes it and gives the focus back to its row. A station that leaves the
// list (forgotten, timed out and hidden, filtered out) closes its field. `calls` are the rows in the order shown.
import { ref, watch } from "vue";
import { stationRowId } from "@/lib/stations";

export function useRowField(calls: () => readonly string[]) {
  const open = ref<string | null>(null);
  watch(calls, (list) => {
    if (open.value !== null && !list.includes(open.value)) open.value = null;
  });

  return {
    open,
    /** A click on a row or Enter on it: the field under it opens, or closes when it is the one open. */
    toggle: (call: string): void => {
      open.value = open.value === call ? null : call;
    },
    /** Up or Down selected the row of `call`: an open field goes under it. */
    follow: (call: string): void => {
      if (open.value !== null) open.value = call;
    },
    /** Esc in the field: it closes, and its row has the focus. */
    close: (): void => {
      const call = open.value;
      open.value = null;
      if (call !== null) document.getElementById(stationRowId(call))?.focus();
    },
  };
}
