// The station panel of the Stations tab (StationPanel, fixed at the bottom of the tab as the box of every tab): which station it shows, one at a time. A click on a row (or Enter on it) shows that station, and so do Up, Down,
// Home and End, which select the next row; the row stays marked in the list, and nothing in the list opens or moves. The cross of the panel or Esc in it closes it and gives the focus back to the row of its station.
// A station that leaves the list (forgotten, timed out and hidden, filtered out) closes the panel. `calls` are the rows in the order shown.
import { ref, watch } from "vue";
import { stationRowId } from "@/lib/stations";

export function useStationPanel(calls: () => readonly string[]) {
  const open = ref<string | null>(null);
  watch(calls, (list) => {
    if (open.value !== null && !list.includes(open.value)) open.value = null;
  });

  return {
    open,
    /** A row was clicked or selected: the panel shows its station. */
    show: (call: string): void => {
      open.value = call;
    },
    /** The cross or Esc: the panel closes, and the row of its station has the focus. */
    close: (): void => {
      const call = open.value;
      open.value = null;
      if (call !== null) document.getElementById(stationRowId(call))?.focus();
    },
  };
}
