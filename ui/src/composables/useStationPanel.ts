// The station panel of the Stations tab: which station it shows, one at a time. A click or Enter
// on a row shows that station, and so do Up, Down, Home and End, which select the next row. The
// cross or Esc closes it and returns focus to the station's row. A station that leaves the list
// closes it. `calls` are the rows in the order shown.
import { ref, watch } from "vue";
import { stationRowId } from "@/lib/stations";

export function useStationPanel(calls: () => readonly string[]) {
  const open = ref<string | null>(null);
  watch(calls, (list) => {
    if (open.value !== null && !list.includes(open.value)) open.value = null;
  });

  return {
    open,
    show: (call: string): void => {
      open.value = call;
    },
    close: (): void => {
      const call = open.value;
      open.value = null;
      if (call !== null) document.getElementById(stationRowId(call))?.focus();
    },
  };
}
