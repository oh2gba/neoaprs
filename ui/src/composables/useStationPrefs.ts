// What the operator has set for each station apart from what it says: its own path (the digipeaters its messages go by) and whether it is RF only. The daemon tells them in one topic, `station_prefs`, the path null where none is set; this splits it into the map and the set the page works with, and sends the changes.
import { computed } from "vue";
import type { Command, StationPref } from "@/protocol/protocol";

export function useStationPrefs(prefs: ReadonlyMap<string, StationPref>, send: (command: Command) => boolean) {
  const paths = computed(() => {
    const own = new Map<string, string>();
    for (const [call, pref] of prefs) if (pref.path !== null) own.set(call, pref.path);
    return own;
  });

  const rfOnly = computed(() => {
    const on = new Set<string>();
    for (const [call, pref] of prefs) if (pref.rf_only) on.add(call);
    return on;
  });

  return {
    paths,
    rfOnly,
    /** Makes everything sent to a station RF only, or not. */
    setRfOnly: (call: string, on: boolean): boolean => send({ cmd: "set_station_rf_only", call, on }),
    /** Gives a station a path of its own (empty is direct). */
    setPath: (call: string, path: string): boolean => send({ cmd: "set_station_path", call, path }),
    clearPath: (call: string): boolean => send({ cmd: "clear_station_path", call }),
  };
}

export type StationPrefs = ReturnType<typeof useStationPrefs>;
