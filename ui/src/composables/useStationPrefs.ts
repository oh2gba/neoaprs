// What the operator has set for each station apart from what it says: its own path (the digipeaters its messages go by), its own timeout (minutes after its last position that it stays on
// the map; 0 is never) and its own attempts (how many times a message to it is transmitted) and whether it is RF only. The daemon tells them in one topic, `station_prefs`, each part null where none is set; this splits it into the maps and the set the page works with, and sends the changes.
import { computed } from "vue";
import type { Command, StationPref } from "@/protocol/protocol";

export function useStationPrefs(prefs: ReadonlyMap<string, StationPref>, send: (command: Command) => boolean) {
  const paths = computed(() => {
    const own = new Map<string, string>();
    for (const [call, pref] of prefs) if (pref.path !== null) own.set(call, pref.path);
    return own;
  });
  const timeouts = computed(() => {
    const own = new Map<string, number>();
    for (const [call, pref] of prefs) if (pref.hide_after_min !== null) own.set(call, pref.hide_after_min);
    return own;
  });

  const attempts = computed(() => {
    const own = new Map<string, number>();
    for (const [call, pref] of prefs) if (pref.attempts !== null) own.set(call, pref.attempts);
    return own;
  });

  const rfOnly = computed(() => {
    const on = new Set<string>();
    for (const [call, pref] of prefs) if (pref.rf_only) on.add(call);
    return on;
  });

  return {
    paths,
    timeouts,
    attempts,
    rfOnly,
    /** Makes everything sent to a station RF only, or not. */
    setRfOnly: (call: string, on: boolean): boolean => send({ cmd: "set_station_rf_only", call, on }),
    /** Gives a station a path of its own (empty is direct). */
    setPath: (call: string, path: string): boolean => send({ cmd: "set_station_path", call, path }),
    clearPath: (call: string): boolean => send({ cmd: "clear_station_path", call }),
    /** Gives a station a timeout of its own (0 is never). */
    setTimeoutMin: (call: string, minutes: number): boolean => send({ cmd: "set_station_timeout", call, minutes }),
    clearTimeoutMin: (call: string): boolean => send({ cmd: "clear_station_timeout", call }),
    /** Gives a station a count of attempts of its own (1 to 10). */
    setAttempts: (call: string, attempts: number): boolean => send({ cmd: "set_station_attempts", call, attempts }),
    clearAttempts: (call: string): boolean => send({ cmd: "clear_station_attempts", call }),
  };
}
