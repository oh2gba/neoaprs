// The two topics of what is known about a station apart from its packets, as tables of rows the page reads: `station_prefs` (what the operator set: its path, RF only, its alert) and `station_keys` (the key it announced for encrypted
// messages), both by call, and what the hub (lib/hub.ts) does with them: replace the whole table, set a row, delete one.
import { shallowReactive } from "vue";
import { fillTable, type Store } from "@/lib/hub";
import type { StationKey, StationPref } from "@/protocol/protocol";

type StationHandlers = Pick<Store, "replaceStationPrefs" | "replaceStationKeys" | "setStationPref" | "setStationKey" | "delStationPref" | "delStationKey">;

export function useStationTables() {
  const stationPrefs = shallowReactive(new Map<string, StationPref>());
  const stationKeys = shallowReactive(new Map<string, StationKey>());
  const handlers: StationHandlers = {
    replaceStationPrefs: (rows) => fillTable(stationPrefs, rows),
    replaceStationKeys: (rows) => fillTable(stationKeys, rows),
    setStationPref: (call, pref) => void stationPrefs.set(call, pref),
    setStationKey: (call, key) => void stationKeys.set(call, key),
    delStationPref: (call) => void stationPrefs.delete(call),
    delStationKey: (call) => void stationKeys.delete(call),
  };
  return { stationPrefs, stationKeys, handlers };
}
