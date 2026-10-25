// The circles under the markers of the map: the ALOHA circle round our own station and the range circle of the selected station, when it is a digipeater that gave a range (composables/useAlohaCircle.ts, composables/useRangeCircles.ts). `add` makes the layers (the ALOHA circle first, so
// the range is over it), `listen` hears the pointer on the ALOHA line.
import type { Ref } from "vue";
import type { Map as MapLibreMap } from "maplibre-gl";
import { useAlohaCircle } from "@/composables/useAlohaCircle";
import { useRangeCircles } from "@/composables/useRangeCircles";

export function useMapCircles(
  map: () => MapLibreMap | null,
  host: Ref<HTMLElement | null>,
  selected: () => string | null,
): { add: (on: MapLibreMap) => void; listen: (on: MapLibreMap) => void } {
  const aloha = useAlohaCircle(map, host);
  const range = useRangeCircles(map, selected);
  return {
    add: (on) => {
      aloha.add(on);
      range.add(on);
    },
    listen: aloha.listen,
  };
}
