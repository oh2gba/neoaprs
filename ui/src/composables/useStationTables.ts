// The tables of rows the page reads of what is known about a station apart from its packets:
// `station_prefs` (path, RF only, alert), `station_keys` and `call_routes` (the radio and paths of
// a call the book does not hold), all by call.
import { shallowReactive } from "vue";
import { fillTable, type Store } from "@/lib/hub";
import type { CallRoute, StationKey, StationPref } from "@/protocol/protocol";

type StationHandlers = Pick<
  Store,
  | "replaceStationPrefs"
  | "replaceStationKeys"
  | "replaceCallRoutes"
  | "setStationPref"
  | "setStationKey"
  | "setCallRoute"
  | "delStationPref"
  | "delStationKey"
  | "delCallRoute"
>;

export function useStationTables() {
  const stationPrefs = shallowReactive(new Map<string, StationPref>());
  const stationKeys = shallowReactive(new Map<string, StationKey>());
  const callRoutes = shallowReactive(new Map<string, CallRoute>());
  const handlers: StationHandlers = {
    replaceStationPrefs: (rows) => fillTable(stationPrefs, rows),
    replaceStationKeys: (rows) => fillTable(stationKeys, rows),
    setStationPref: (call, pref) => void stationPrefs.set(call, pref),
    setStationKey: (call, key) => void stationKeys.set(call, key),
    delStationPref: (call) => void stationPrefs.delete(call),
    delStationKey: (call) => void stationKeys.delete(call),
    replaceCallRoutes: (rows) => fillTable(callRoutes, rows),
    setCallRoute: (call, route) => void callRoutes.set(call, route),
    delCallRoute: (call) => void callRoutes.delete(call),
  };
  return { stationPrefs, stationKeys, callRoutes, handlers };
}
