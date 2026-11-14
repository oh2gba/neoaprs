// The ships and the aircraft of the map as the page holds them: the topics `ships` (by MMSI) and `aircraft` (by ICAO address), and `traffic`, the state of their two feeds; and what the hub (lib/hub.ts) does with them: replace a
// whole table, set a row, delete one. Only received: nothing of them is ever sent.
import { shallowReactive, shallowRef } from "vue";
import type { Store } from "@/lib/hub";
import type { AircraftRow, ShipRow, TrafficState } from "@/protocol/protocol";

type TrafficHandlers = Pick<Store, "replaceShips" | "replaceAircraft" | "replaceTraffic" | "setShip" | "setAircraft" | "delShip" | "delAircraft">;

function fill<T>(into: Map<string, T>, rows: Record<string, T>): void {
  into.clear();
  for (const [key, row] of Object.entries(rows)) into.set(key, row);
}

export function useTrafficTables() {
  const ships = shallowReactive(new Map<string, ShipRow>());
  const aircraft = shallowReactive(new Map<string, AircraftRow>());
  const traffic = shallowRef<TrafficState | null>(null);
  const handlers: TrafficHandlers = {
    replaceShips: (rows) => fill(ships, rows),
    replaceAircraft: (rows) => fill(aircraft, rows),
    replaceTraffic: (value) => (traffic.value = value),
    setShip: (key, row) => void ships.set(key, row),
    setAircraft: (key, row) => void aircraft.set(key, row),
    delShip: (key) => void ships.delete(key),
    delAircraft: (key) => void aircraft.delete(key),
  };
  return { ships, aircraft, traffic, handlers };
}
