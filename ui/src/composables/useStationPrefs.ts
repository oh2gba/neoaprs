// What the operator has set for each station apart from what it says: its own path (the digipeaters its messages go by), whether it is RF only, and its alert (when to be told about it). The daemon tells them in one topic, `station_prefs`, the path and the alert null where
// none is set; this splits it into the maps and the set the page works with, and sends the changes.
import { computed } from "vue";
import type { AlertWhen, Command, StationPref } from "@/protocol/protocol";

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

  const alerts = computed(() => {
    const set = new Map<string, AlertWhen>();
    for (const [call, pref] of prefs) if (pref.alert !== null) set.set(call, pref.alert);
    return set;
  });

  return {
    paths,
    rfOnly,
    alerts,
    /** Sets when the operator is told about a station; one that watches nothing takes it away. */
    setAlert: (call: string, alert: AlertWhen): boolean => send({ cmd: "set_station_alert", call, ...alert }),
    /** Makes everything sent to a station RF only, or not. */
    setRfOnly: (call: string, on: boolean): boolean => send({ cmd: "set_station_rf_only", call, on }),
    /** Gives a station a path of its own (empty is direct). */
    setPath: (call: string, path: string): boolean => send({ cmd: "set_station_path", call, path }),
    clearPath: (call: string): boolean => send({ cmd: "clear_station_path", call }),
  };
}

export type StationPrefs = ReturnType<typeof useStationPrefs>;
