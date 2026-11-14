// The ships and the aircraft on the map (components/StationMap.vue): their layers made again with every style (lib/trafficlayers.ts), drawn again when the topics change, and the card of the one that was clicked
// (components/TrafficCard.vue), which goes when it leaves the feed or its switch is turned off. A pointer over one shows that it can be clicked.
import { computed, ref, watch } from "vue";
import type { Map as MapLibreMap, MapLayerMouseEvent } from "maplibre-gl";
import { aircraftFeatures, shipFeatures, type TrafficKind, type TrafficPick } from "@/lib/traffic";
import { AIRCRAFT_LAYER, SHIPS_LAYER, addTrafficLayers, setTrafficData } from "@/lib/trafficlayers";
import type { AircraftRow, ShipRow } from "@/protocol/protocol";

interface Traffic {
  ships: ReadonlyMap<string, ShipRow>;
  aircraft: ReadonlyMap<string, AircraftRow>;
}

export function useTrafficMap(mapOf: () => MapLibreMap | null, traffic: Traffic) {
  const picked = ref<TrafficPick | null>(null);
  const ship = computed(() => (picked.value?.kind === "ship" ? traffic.ships.get(picked.value.key) : undefined));
  const aircraft = computed(() => (picked.value?.kind === "aircraft" ? traffic.aircraft.get(picked.value.key) : undefined));

  function draw(): void {
    const map = mapOf();
    if (!map) return;
    const pick = picked.value;
    setTrafficData(
      map,
      shipFeatures(traffic.ships.values(), pick?.kind === "ship" ? pick.key : null),
      aircraftFeatures(traffic.aircraft.values(), pick?.kind === "aircraft" ? pick.key : null),
    );
  }

  function add(): void {
    const map = mapOf();
    if (!map) return;
    addTrafficLayers(map);
    draw();
  }

  const pickOn =
    (kind: TrafficKind) =>
    (event?: MapLayerMouseEvent): void => {
      const key: unknown = event?.features?.[0]?.properties["key"];
      if (typeof key === "string" || typeof key === "number") picked.value = { kind, key: String(key) };
    };

  function cursor(map: MapLibreMap, pointer: boolean): void {
    const canvas = (map as Partial<Pick<MapLibreMap, "getCanvas">>).getCanvas?.call(map);
    if (canvas) canvas.style.cursor = pointer ? "pointer" : "";
  }

  /** The clicks and the pointer on the two layers, once, when the map is made. */
  function listen(map: MapLibreMap): void {
    for (const [layer, kind] of [
      [SHIPS_LAYER, "ship"],
      [AIRCRAFT_LAYER, "aircraft"],
    ] as const) {
      map.on("click", layer, pickOn(kind));
      map.on("mouseenter", layer, () => cursor(map, true));
      map.on("mouseleave", layer, () => cursor(map, false));
    }
  }

  const close = (): void => void (picked.value = null);

  watch([() => [...traffic.ships.values()], () => [...traffic.aircraft.values()], picked], draw);
  watch([ship, aircraft], ([s, a]) => {
    if (picked.value && s === undefined && a === undefined) close(); // (it left the feed)
  });

  return { picked, ship, aircraft, add, listen, close };
}
